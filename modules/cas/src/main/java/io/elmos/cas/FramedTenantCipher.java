package io.elmos.cas;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Versioned, bounded AES-GCM frames; uses the existing tenant provider once per object key. */
final class FramedTenantCipher {
    static final byte[] MAGIC = "ELMOS-CAS-ENC/3\n".getBytes(StandardCharsets.US_ASCII);
    static final int CHUNK_BYTES = 64 * 1024;
    private static final int DESCRIPTOR_BYTES = 32 + 64 + Long.BYTES;
    private static final SecureRandom RANDOM = new SecureRandom();

    private FramedTenantCipher() { }

    static void write(TenantEncryption encryption, String tenant, CasDigest digest,
                      InputStream plaintext, OutputStream destination) throws IOException {
        byte[] key = new byte[32];
        byte[] prefix = new byte[8];
        RANDOM.nextBytes(key);
        RANDOM.nextBytes(prefix);
        byte[] descriptor = descriptor(key, digest);
        try {
            CasDigest descriptorDigest = CasDigest.of(descriptor);
            TenantEncryption.Envelope envelope = encryption.seal(tenant, descriptorDigest, descriptor);
            byte[] ciphertext = envelope.ciphertext();
            byte[] keyId = envelope.keyId().getBytes(StandardCharsets.US_ASCII);
            if (keyId.length < 1 || keyId.length > 64 || ciphertext.length > maximumWrappedBytes(encryption)) {
                throw new IllegalArgumentException("streaming key envelope is outside policy");
            }
            DataOutputStream output = new DataOutputStream(destination);
            output.write(MAGIC);
            output.write(descriptorDigest.hex().getBytes(StandardCharsets.US_ASCII));
            output.writeByte(keyId.length);
            output.write(keyId);
            output.writeInt(ciphertext.length);
            output.write(ciphertext);
            output.write(prefix);
            Arrays.fill(ciphertext, (byte) 0);
            long remaining = digest.sizeBytes();
            int index = 0;
            do {
                int count = (int) Math.min(CHUNK_BYTES, remaining);
                byte[] chunk = plaintext.readNBytes(count);
                if (chunk.length != count) throw new IOException("verified plaintext spool was truncated");
                try {
                    output.write(transform(Cipher.ENCRYPT_MODE, key, prefix, index++,
                            tenant, digest, descriptorDigest, count, chunk));
                } finally { Arrays.fill(chunk, (byte) 0); }
                remaining -= count;
            } while (remaining > 0);
            if (plaintext.read() != -1) throw new IOException("verified plaintext spool grew");
            // A key revoked during a long encryption must not authorize the resulting object.
            byte[] reopened = encryption.open(tenant, descriptorDigest, envelope);
            try {
                if (!java.security.MessageDigest.isEqual(descriptor, reopened)) {
                    throw corrupt(digest);
                }
            } finally { Arrays.fill(reopened, (byte) 0); }
        } finally {
            Arrays.fill(key, (byte) 0);
            Arrays.fill(descriptor, (byte) 0);
        }
    }

    /** The returned stream is INTERNAL ONLY: the store consumes it into verified private staging. */
    static InputStream decrypt(TenantEncryption encryption, String tenant, CasDigest digest,
                               InputStream source) throws IOException {
        DataInputStream input = new DataInputStream(source);
        String hex = new String(exact(input, 64), StandardCharsets.US_ASCII);
        CasDigest descriptorDigest;
        try { descriptorDigest = new CasDigest(CasDigest.ALGORITHM, hex, DESCRIPTOR_BYTES); }
        catch (IllegalArgumentException malformed) { throw corrupt(digest); }
        int keyLength = input.readUnsignedByte();
        if (keyLength < 1 || keyLength > 64) throw corrupt(digest);
        String keyId = new String(exact(input, keyLength), StandardCharsets.US_ASCII);
        int wrappedLength = input.readInt();
        if (wrappedLength < 1 || wrappedLength > maximumWrappedBytes(encryption)) throw corrupt(digest);
        TenantEncryption.Envelope envelope = new TenantEncryption.Envelope(keyId, exact(input, wrappedLength));
        byte[] prefix = exact(input, 8);
        byte[] descriptor = encryption.open(tenant, descriptorDigest, envelope);
        byte[] key;
        try {
            if (descriptor.length != DESCRIPTOR_BYTES || !CasDigest.of(descriptor).equals(descriptorDigest)) {
                throw corrupt(digest);
            }
            key = Arrays.copyOf(descriptor, 32);
            if (!java.security.MessageDigest.isEqual(descriptor, descriptor(key, digest))) {
                Arrays.fill(key, (byte) 0);
                throw corrupt(digest);
            }
        } finally { Arrays.fill(descriptor, (byte) 0); }
        return new InputStream() {
            private long remaining = digest.sizeBytes();
            private int index;
            private byte[] chunk = new byte[0];
            private int position;
            private boolean finished;

            @Override public int read() throws IOException {
                byte[] one = new byte[1];
                return read(one, 0, 1) < 0 ? -1 : Byte.toUnsignedInt(one[0]);
            }

            @Override public int read(byte[] buffer, int offset, int length) throws IOException {
                java.util.Objects.checkFromIndexSize(offset, length, buffer.length);
                if (length == 0) return 0;
                if (position == chunk.length) {
                    Arrays.fill(chunk, (byte) 0);
                    if (finished) return -1;
                    if (index > 0 && remaining == 0) {
                        if (input.read() != -1) throw corrupt(digest);
                        byte[] reopened = encryption.open(tenant, descriptorDigest, envelope);
                        try {
                            if (!java.security.MessageDigest.isEqual(reopened, descriptor(key, digest))) {
                                throw corrupt(digest);
                            }
                        } finally { Arrays.fill(reopened, (byte) 0); }
                        finished = true;
                        return -1;
                    }
                    int count = (int) Math.min(CHUNK_BYTES, remaining);
                    try {
                        chunk = transform(Cipher.DECRYPT_MODE, key, prefix, index++, tenant,
                                digest, descriptorDigest, count, exact(input, count + 16));
                    } catch (java.io.EOFException truncated) { throw corrupt(digest); }
                    remaining -= count;
                    position = 0;
                    if (count == 0) return read(buffer, offset, length);
                }
                int count = Math.min(length, chunk.length - position);
                System.arraycopy(chunk, position, buffer, offset, count);
                position += count;
                return count;
            }

            @Override public void close() throws IOException {
                Arrays.fill(key, (byte) 0);
                Arrays.fill(chunk, (byte) 0);
                finished = true;
                input.close();
            }
        };
    }

    static long maximumPhysicalBytes(TenantEncryption encryption, long size) {
        long frames = Math.max(1, (size + CHUNK_BYTES - 1) / CHUNK_BYTES);
        return Math.addExact(Math.addExact(size, Math.multiplyExact(frames, 16)),
                MAGIC.length + 64L + 1 + 64 + 4 + maximumWrappedBytes(encryption) + 8);
    }

    private static int maximumWrappedBytes(TenantEncryption encryption) {
        long maximum = encryption.maximumEnvelopeOverheadBytes();
        if (maximum < 64 || maximum > 1024 * 1024) {
            throw new IllegalArgumentException("tenant encryption envelope overhead is outside streaming policy");
        }
        return Math.toIntExact(DESCRIPTOR_BYTES + maximum);
    }

    private static byte[] descriptor(byte[] key, CasDigest digest) {
        return ByteBuffer.allocate(DESCRIPTOR_BYTES).put(key)
                .put(digest.hex().getBytes(StandardCharsets.US_ASCII)).putLong(digest.sizeBytes()).array();
    }

    private static byte[] exact(InputStream input, int size) throws IOException {
        byte[] bytes = input.readNBytes(size);
        if (bytes.length != size) throw new java.io.EOFException("encrypted frame is truncated");
        return bytes;
    }

    private static byte[] transform(int mode, byte[] key, byte[] prefix, int index, String tenant,
                                    CasDigest digest, CasDigest descriptor, int size, byte[] input) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            byte[] nonce = ByteBuffer.allocate(12).put(prefix).putInt(index).array();
            cipher.init(mode, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(("elmos-cas-framed/3\n" + tenant + "\n" + digest.compact() + "\n"
                    + descriptor.compact() + "\n" + index + ":" + size).getBytes(StandardCharsets.UTF_8));
            return cipher.doFinal(input);
        } catch (AEADBadTagException invalid) {
            throw corrupt(digest);
        } catch (GeneralSecurityException unavailable) {
            throw new IllegalStateException("streaming AES-GCM provider unavailable", unavailable);
        }
    }

    private static CasExceptions.CasCorruptionException corrupt(CasDigest digest) {
        return new CasExceptions.CasCorruptionException("tenant-encrypted stream", digest,
                CasDigest.ofUtf8("invalid encrypted stream"));
    }
}
