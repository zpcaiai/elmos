public class Arith {
    public static int wrapAdd(int a, int b) { return a + b; }
    public static int wrapMul(int a, int b) { return a * b; }
    public static int div(int a, int b) { return a / b; }
    public static int rem(int a, int b) { return a % b; }
    public static long longMul(int a, int b) { return (long) a * (long) b; }
    public static int shiftLeft(int a, int b) { return a << b; }
    public static int shiftRight(int a, int b) { return a >> b; }
    public static int unsignedShift(int a, int b) { return a >>> b; }
    public static int narrow(int a) { return (byte) a; }
    public static int toChar(int a) { return (char) a; }
    public static double ratio(int a, int b) { return (double) a / b; }
    public static int truncate(double d) { return (int) d; }
    public static int absolute(int a) { return Math.abs(a); }
    // int << long is an int shift: the distance masks to 5 bits, not 6.
    public static int shiftByLong(int a, long b) { return a << b; }
    public static long longShift(long a, int b) { return a << b; }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        int b = Integer.parseInt(args[1]);
        System.out.println("add=" + wrapAdd(a, b));
        System.out.println("mul=" + wrapMul(a, b));
        System.out.println("longMul=" + longMul(a, b));
        System.out.println("shl=" + shiftLeft(a, b));
        System.out.println("shr=" + shiftRight(a, b));
        System.out.println("ushr=" + unsignedShift(a, b));
        System.out.println("byte=" + narrow(a));
        System.out.println("char=" + toChar(a));
        System.out.println("abs=" + absolute(a));
        System.out.println("ratio=" + ratio(a, b));
        System.out.println("trunc=" + truncate(ratio(a, b)));
        System.out.println("neg=" + (-a));
        System.out.println("not=" + (~a));
        System.out.println("div=" + div(a, b));
        System.out.println("rem=" + rem(a, b));
        System.out.println("shlLong=" + shiftByLong(a, (long) b));
        System.out.println("longShl=" + longShift((long) a, b));
    }
}
