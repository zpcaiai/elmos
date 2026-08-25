package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MerkleTreeTest {

    private static CasDigest blob(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    @Test void inputOrderDoesNotChangeTheRootDigest() {
        List<MerkleTree.FileNode> ascending = List.of(
                new MerkleTree.FileNode("src/a.java", blob("a"), false),
                new MerkleTree.FileNode("src/b.java", blob("b"), false),
                new MerkleTree.FileNode("pom.xml", blob("pom"), false));
        List<MerkleTree.FileNode> shuffled = List.of(
                new MerkleTree.FileNode("pom.xml", blob("pom"), false),
                new MerkleTree.FileNode("src/b.java", blob("b"), false),
                new MerkleTree.FileNode("src/a.java", blob("a"), false));
        assertEquals(MerkleTree.canonicalize(ascending, List.of()).rootDigest(),
                MerkleTree.canonicalize(shuffled, List.of()).rootDigest());
    }

    @Test void executableBitAndSymlinkTargetArePartOfTheIdentity() {
        var plain = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("run.sh", blob("#!/bin/sh"), false)), List.of());
        var executable = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("run.sh", blob("#!/bin/sh"), true)), List.of());
        assertNotEquals(plain.rootDigest(), executable.rootDigest());

        var toA = MerkleTree.canonicalize(List.of(), List.of(new MerkleTree.SymlinkNode("link", "a")));
        var toB = MerkleTree.canonicalize(List.of(), List.of(new MerkleTree.SymlinkNode("link", "b")));
        assertNotEquals(toA.rootDigest(), toB.rootDigest());
        assertEquals(1, toA.symlinkCount());
    }

    @Test void lineEndingsAreNeverNormalisedAway() {
        var lf = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a.txt", blob("one\ntwo"), false)), List.of());
        var crlf = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a.txt", blob("one\r\ntwo"), false)), List.of());
        assertNotEquals(lf.rootDigest(), crlf.rootDigest());
    }

    @Test void nestedDirectoriesProduceOneTreeObjectPerDirectory() {
        var tree = MerkleTree.canonicalize(List.of(
                new MerkleTree.FileNode("src/main/java/A.java", blob("A"), false),
                new MerkleTree.FileNode("src/main/java/B.java", blob("B"), false),
                new MerkleTree.FileNode("README.md", blob("readme"), false)), List.of());
        assertEquals(4, tree.treeObjects().size());
        assertEquals(3, tree.fileCount());
        assertEquals(blob("A").sizeBytes() + blob("B").sizeBytes() + blob("readme").sizeBytes(),
                tree.totalFileBytes());
    }

    @Test void serialisedTreeRoundTripsThroughTheParser() {
        var tree = MerkleTree.canonicalize(List.of(
                new MerkleTree.FileNode("dir/x", blob("x"), true),
                new MerkleTree.FileNode("y", blob("y"), false)), List.of());
        MerkleTree.TreeObject root = tree.treeObjects().get(tree.treeObjects().size() - 1);
        List<MerkleTree.Entry> entries = MerkleTree.parse(root.bytes());
        assertEquals(2, entries.size());
        assertEquals("dir", entries.get(0).name());
        assertEquals(MerkleTree.EntryKind.DIRECTORY, entries.get(0).kind());
        assertEquals("y", entries.get(1).name());
        assertEquals(MerkleTree.MODE_FILE, entries.get(1).mode());
    }

    @Test void namesCannotForgeTheRecordSeparator() {
        assertThrows(IllegalArgumentException.class,
                () -> new MerkleTree.Entry("a\tb", MerkleTree.EntryKind.FILE, MerkleTree.MODE_FILE, "x"));
        assertThrows(IllegalArgumentException.class,
                () -> MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a\nb", blob("x"), false)), List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a/../b", blob("x"), false)), List.of()));
    }

    @Test void conflictingPathsAreRefusedRatherThanResolvedByOrder() {
        assertThrows(IllegalArgumentException.class, () -> MerkleTree.canonicalize(List.of(
                new MerkleTree.FileNode("a", blob("1"), false),
                new MerkleTree.FileNode("a", blob("2"), false)), List.of()));
        assertThrows(IllegalArgumentException.class, () -> MerkleTree.canonicalize(List.of(
                new MerkleTree.FileNode("a", blob("1"), false),
                new MerkleTree.FileNode("a/b", blob("2"), false)), List.of()));
    }

    @Test void namesAreOrderedByUtf8BytesNotUtf16CodeUnits() {
        // U+FF21 (0xEF 0xBC 0xA1) sorts after U+10000 in UTF-16 but before it in UTF-8.
        String supplementary = new String(Character.toChars(0x10000));
        String fullWidthA = "Ａ";
        assertTrue(MerkleTree.compareUtf8(fullWidthA, supplementary) < 0);
        assertTrue(fullWidthA.compareTo(supplementary) > 0);
    }
}
