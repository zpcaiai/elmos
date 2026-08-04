public class Failure {
    public static int risky(int a, int b) {
        int[] xs = new int[3];
        xs[0] = a;
        xs[1] = b;
        try {
            xs[2] = a / b;
        } catch (ArithmeticException e) {
            xs[2] = -1;
        } finally {
            xs[0] = xs[0] + 1;
        }
        return xs[0] + xs[1] + xs[2];
    }
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        int b = Integer.parseInt(args[1]);
        System.out.println("risky=" + risky(a, b));
        int[] arr = {1, 2, 3};
        System.out.println("len=" + arr.length);
        int total = 0;
        for (int x : arr) { total += x; }
        System.out.println("total=" + total);
        if (b == 0) { throw new IllegalStateException("b was zero"); }
        System.out.println("idx=" + arr[a % 5]);
    }
}
