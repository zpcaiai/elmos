public final class Decision {
    public static boolean decision(boolean left, boolean right, boolean fallback) {
        if ((left && right) || fallback) { return true; }
        return false;
    }
}
