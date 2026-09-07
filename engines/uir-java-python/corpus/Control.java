public class Control {
    public static int loops(int n) {
        int total = 0;
        for (int i = 0; i < n; i++) {
            if (i % 3 == 0) { continue; }
            if (i > 50) { break; }
            total += i;
        }
        int j = 0;
        while (j < n) { total -= j; j += 2; }
        do { total++; } while (total < 0);
        return total;
    }
    public static String classify(int n) {
        switch (n % 4) {
            case 0: return "zero";
            case 1: return "one";
            case 2: return "two";
            default: return "other";
        }
    }
    public static int ternary(int a, int b) { return a > b ? a - b : b - a; }
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        int b = Integer.parseInt(args[1]);
        System.out.println("loops=" + loops(a % 100));
        System.out.println("class=" + classify(a));
        System.out.println("tern=" + ternary(a, b));
        boolean flag = a > 0 && b > 0 || a == b;
        System.out.println("flag=" + flag);
        System.out.println("xor=" + ((a > 0) ^ (b > 0)));
    }
}
