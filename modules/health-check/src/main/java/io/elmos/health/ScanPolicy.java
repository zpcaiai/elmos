package io.elmos.health;

public record ScanPolicy(int maxFiles, long maxBytesPerFile, long maxTotalBytes,
                         int oversizedClassLines, int complexMethodBranches) {
    public ScanPolicy {
        if (maxFiles < 1 || maxFiles > 2_000_000 || maxBytesPerFile < 1024 || maxBytesPerFile > 20_000_000
                || maxTotalBytes < maxBytesPerFile || maxTotalBytes > 20_000_000_000L
                || oversizedClassLines < 100 || complexMethodBranches < 5) {
            throw new IllegalArgumentException("health scan policy is outside safe bounds");
        }
    }

    public static ScanPolicy defaults() {
        return new ScanPolicy(200_000, 2_000_000, 2_000_000_000L, 600, 20);
    }
}
