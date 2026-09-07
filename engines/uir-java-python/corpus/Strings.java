public class Strings {
    public static String describe(int n, char c) {
        return "n=" + n + " c=" + c + " sum=" + (c + n) + " cat=" + ("" + c);
    }
    public static String build(String s, int times) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < times; i++) { sb.append(s).append(i).append('-'); }
        return sb.toString();
    }
    public static void main(String[] args) {
        int n = Integer.parseInt(args[0]);
        String s = args[1];
        char c = s.charAt(0);
        System.out.println(describe(n, c));
        System.out.println(build(s, 3));
        System.out.println("len=" + s.length());
        System.out.println("up=" + s.toUpperCase());
        System.out.println("sub=" + s.substring(0, 1));
        System.out.println("idx=" + s.indexOf("a"));
        System.out.println("eq=" + s.equals("abc"));
        System.out.println("empty=" + s.isEmpty());
        System.out.println("bool=" + (n > 0));
        System.out.println("dbl=" + (n / 4.0));
        System.out.println("big=" + (n * 1.0E7));
        System.out.println("small=" + (n / 1.0E7));
        System.out.println("nul=" + null);
        System.out.println("valueOf=" + String.valueOf(n));
        System.out.println();
        System.out.println((Object) null);
    }
}
