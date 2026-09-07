package io.elmos.cas;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/**
 * ELMOS-CAS-003. Canonical directory serialisation.
 *
 * <p>The tree object is what makes two checkouts of the same commit hash to the same value on
 * two different machines. Everything that a filesystem is allowed to vary - entry order,
 * inode numbers, timestamps, owners, permission bits beyond the executable bit - is either
 * fixed here or excluded. What is <em>not</em> excluded is the executable bit and the symlink
 * target, because both change what a build does.
 *
 * <p>File content bytes are never touched. ELMOS-CAS-004: no line-ending translation, no
 * charset sniffing, no BOM handling. A CRLF file and its LF twin are two different objects and
 * the cache must be able to tell them apart, because the compiler can.
 *
 * <p>Serialisation format, one entry per line, entries sorted by UTF-8 byte order of the name:
 * <pre>
 * elmos-tree/1\n
 * &lt;mode&gt;\t&lt;kind&gt;\t&lt;name&gt;\t&lt;payload&gt;\n
 * </pre>
 * The name is validated to exclude tab, newline and slash, so the record separator cannot be
 * forged from inside a filename.
 */
public final class MerkleTree {

    public static final String FORMAT = "elmos-tree/1";
    public static final String MODE_FILE = "100644";
    public static final String MODE_EXECUTABLE = "100755";
    public static final String MODE_SYMLINK = "120000";
    public static final String MODE_DIRECTORY = "040000";

    private MerkleTree() {
    }

    public enum EntryKind {
        FILE,
        SYMLINK,
        DIRECTORY
    }

    /** One line of a serialised tree. {@code payload} is a digest for FILE/DIRECTORY, a target for SYMLINK. */
    public record Entry(String name, EntryKind kind, String mode, String payload) implements Comparable<Entry> {
        public Entry {
            validateName(name);
            Objects.requireNonNull(kind, "kind");
            CasText.required(mode, "mode");
            CasText.required(payload, "payload");
        }

        @Override
        public int compareTo(Entry other) {
            return compareUtf8(name, other.name);
        }
    }

    /** A serialised tree object, ready to be stored in the CAS under {@link #digest()}. */
    public record TreeObject(CasDigest digest, byte[] bytes, List<Entry> entries) {
        public TreeObject {
            Objects.requireNonNull(digest, "digest");
            bytes = bytes.clone();
            entries = List.copyOf(entries);
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    /**
     * The whole canonical form of a directory: the root digest plus every tree object that must
     * be present in the store for the root to be resolvable.
     */
    public record CanonicalTree(CasDigest rootDigest,
                                List<TreeObject> treeObjects,
                                int fileCount,
                                int symlinkCount,
                                long totalFileBytes) {
        public CanonicalTree {
            Objects.requireNonNull(rootDigest, "rootDigest");
            treeObjects = List.copyOf(treeObjects);
        }
    }

    public record FileNode(String path, CasDigest content, boolean executable) {
        public FileNode {
            validatePath(path);
            Objects.requireNonNull(content, "content");
        }
    }

    public record SymlinkNode(String path, String target) {
        public SymlinkNode {
            validatePath(path);
            CasText.required(target, "target");
            if (target.indexOf('\n') >= 0 || target.indexOf('\t') >= 0 || target.indexOf('\0') >= 0) {
                throw new IllegalArgumentException("symlink target must not contain separator characters: " + target);
            }
        }
    }

    /**
     * Builds the canonical tree for a flat listing.
     *
     * @throws IllegalArgumentException if two nodes claim the same path, or if a path would need
     *                                  a directory where a file already sits. Both are real
     *                                  conditions when a snapshot is assembled from overlays, and
     *                                  silently letting the last writer win would make the root
     *                                  digest depend on iteration order.
     */
    public static CanonicalTree canonicalize(List<FileNode> files, List<SymlinkNode> symlinks) {
        Node root = new Node();
        for (FileNode file : files) {
            insert(root, file.path()).setFile(file);
        }
        for (SymlinkNode symlink : symlinks) {
            insert(root, symlink.path()).setSymlink(symlink);
        }
        List<TreeObject> objects = new ArrayList<>();
        Counters counters = new Counters();
        CasDigest rootDigest = serialize(root, objects, counters);
        return new CanonicalTree(rootDigest, objects, counters.files, counters.symlinks, counters.bytes);
    }

    public static TreeObject serializeEntries(List<Entry> entries) {
        List<Entry> sorted = new ArrayList<>(entries);
        sorted.sort(Entry::compareTo);
        for (int index = 1; index < sorted.size(); index++) {
            if (sorted.get(index).name().equals(sorted.get(index - 1).name())) {
                throw new IllegalArgumentException("duplicate tree entry: " + sorted.get(index).name());
            }
        }
        StringBuilder builder = new StringBuilder(FORMAT).append('\n');
        for (Entry entry : sorted) {
            builder.append(entry.mode()).append('\t')
                    .append(entry.kind().name()).append('\t')
                    .append(entry.name()).append('\t')
                    .append(entry.payload()).append('\n');
        }
        byte[] bytes = builder.toString().getBytes(StandardCharsets.UTF_8);
        return new TreeObject(CasDigest.of(bytes), bytes, sorted);
    }

    public static List<Entry> parse(byte[] treeBytes) {
        String text = new String(treeBytes, StandardCharsets.UTF_8);
        String[] lines = text.split("\n", -1);
        if (lines.length == 0 || !FORMAT.equals(lines[0])) {
            throw new IllegalArgumentException("not an " + FORMAT + " object");
        }
        List<Entry> entries = new ArrayList<>();
        for (int index = 1; index < lines.length; index++) {
            String line = lines[index];
            if (line.isEmpty()) {
                continue;
            }
            String[] fields = line.split("\t", -1);
            if (fields.length != 4) {
                throw new IllegalArgumentException("malformed tree line: " + line);
            }
            entries.add(new Entry(fields[2], EntryKind.valueOf(fields[1]), fields[0], fields[3]));
        }
        return List.copyOf(entries);
    }

    private static CasDigest serialize(Node node, List<TreeObject> sink, Counters counters) {
        List<Entry> entries = new ArrayList<>();
        for (Map.Entry<String, Node> child : node.children.entrySet()) {
            Node value = child.getValue();
            if (value.file != null) {
                counters.files++;
                counters.bytes += value.file.content().sizeBytes();
                entries.add(new Entry(child.getKey(), EntryKind.FILE,
                        value.file.executable() ? MODE_EXECUTABLE : MODE_FILE, value.file.content().compact()));
            } else if (value.symlink != null) {
                counters.symlinks++;
                entries.add(new Entry(child.getKey(), EntryKind.SYMLINK, MODE_SYMLINK, value.symlink.target()));
            } else {
                CasDigest childDigest = serialize(value, sink, counters);
                entries.add(new Entry(child.getKey(), EntryKind.DIRECTORY, MODE_DIRECTORY, childDigest.compact()));
            }
        }
        TreeObject object = serializeEntries(entries);
        sink.add(object);
        return object.digest();
    }

    private static Node insert(Node root, String path) {
        Node current = root;
        String[] segments = path.split("/");
        for (int index = 0; index < segments.length; index++) {
            String segment = segments[index];
            validateName(segment);
            boolean last = index == segments.length - 1;
            Node next = current.children.get(segment);
            if (next == null) {
                next = new Node();
                current.children.put(segment, next);
            } else if (!last && (next.file != null || next.symlink != null)) {
                throw new IllegalArgumentException("path traverses a non-directory: " + path);
            }
            current = next;
        }
        if (!current.children.isEmpty()) {
            throw new IllegalArgumentException("path is already a directory: " + path);
        }
        return current;
    }

    private static void validatePath(String path) {
        CasText.required(path, "path");
        if (path.startsWith("/") || path.endsWith("/") || path.contains("//")) {
            throw new IllegalArgumentException("path must be relative and normalised: " + path);
        }
    }

    private static void validateName(String name) {
        CasText.required(name, "name");
        if (name.equals(".") || name.equals("..")) {
            throw new IllegalArgumentException("path segment must not be a relative reference: " + name);
        }
        if (name.indexOf('/') >= 0 || name.indexOf('\t') >= 0 || name.indexOf('\n') >= 0 || name.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("path segment contains a separator character: " + name);
        }
    }

    /**
     * Sorts by UTF-8 bytes rather than by {@link String#compareTo}. Java compares UTF-16 code
     * units, which orders supplementary-plane names before some BMP names; two runners on the
     * same content would then produce two different root digests.
     */
    static int compareUtf8(String left, String right) {
        byte[] a = left.getBytes(StandardCharsets.UTF_8);
        byte[] b = right.getBytes(StandardCharsets.UTF_8);
        int limit = Math.min(a.length, b.length);
        for (int index = 0; index < limit; index++) {
            int diff = (a[index] & 0xff) - (b[index] & 0xff);
            if (diff != 0) {
                return diff;
            }
        }
        return a.length - b.length;
    }

    private static final class Node {
        private final Map<String, Node> children = new TreeMap<>(MerkleTree::compareUtf8);
        private FileNode file;
        private SymlinkNode symlink;

        void setFile(FileNode value) {
            requireUnclaimed();
            this.file = value;
        }

        void setSymlink(SymlinkNode value) {
            requireUnclaimed();
            this.symlink = value;
        }

        private void requireUnclaimed() {
            if (file != null || symlink != null) {
                throw new IllegalArgumentException("duplicate path in tree input");
            }
        }
    }

    private static final class Counters {
        private int files;
        private int symlinks;
        private long bytes;
    }

    /** Convenience for callers that only have an ordered map of path to content. */
    public static CanonicalTree ofFiles(Map<String, CasDigest> files) {
        List<FileNode> nodes = new ArrayList<>();
        new LinkedHashMap<>(files).forEach((path, digest) -> nodes.add(new FileNode(path, digest, false)));
        return canonicalize(nodes, List.of());
    }
}
