package com.giftfuture.chinapubcf.service;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

@Service
public class PasswordService {
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(12);

    public String encode(String rawPassword) {
        requireStrongPassword(rawPassword);
        return encoder.encode(rawPassword);
    }

    public String encodeVerifiedLegacy(String rawPassword) {
        if (rawPassword == null || rawPassword.isEmpty() || rawPassword.length() > 72) {
            throw new IllegalArgumentException("legacy password cannot be upgraded");
        }
        return encoder.encode(rawPassword);
    }

    public boolean matches(String rawPassword, String storedHash) {
        if (storedHash == null || rawPassword == null) {
            return false;
        }
        if (storedHash.startsWith("$2")) {
            return encoder.matches(rawPassword, storedHash);
        }
        return storedHash.matches("(?i)[0-9a-f]{32}")
                && MessageDigest.isEqual(legacyMd5(rawPassword).getBytes(StandardCharsets.US_ASCII),
                storedHash.toUpperCase().getBytes(StandardCharsets.US_ASCII));
    }

    public boolean needsUpgrade(String storedHash) {
        return storedHash != null && !storedHash.startsWith("$2");
    }

    private static void requireStrongPassword(String rawPassword) {
        if (rawPassword == null || rawPassword.length() < 8 || rawPassword.length() > 72) {
            throw new IllegalArgumentException("password length must be between 8 and 72 characters");
        }
    }

    static String legacyMd5(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("MD5");
            return HexFormat.of().withUpperCase().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("MD5 unavailable for legacy verification", impossible);
        }
    }
}
