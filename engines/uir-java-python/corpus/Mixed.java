public class Mixed {
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        int i = a;
        i += 2.5;
        System.out.println("compound=" + i);
        long l = a;
        l *= 1000000007L;
        System.out.println("longCompound=" + l);
        int k = a;
        k /= 3;
        System.out.println("divCompound=" + k);
        int m = a;
        m %= 3;
        System.out.println("remCompound=" + m);
        double d = a;
        d /= 4;
        System.out.println("dblCompound=" + d);
        char c = (char) ('a' + (a & 7));
        c += 1;
        System.out.println("charCompound=" + c);
        String s = "v";
        s += a;
        s += '!';
        System.out.println("strCompound=" + s);
        byte bt = (byte) a;
        bt += 200;
        System.out.println("byteCompound=" + bt);
        int[] xs = new int[4];
        int idx = a & 3;
        xs[idx] += a;
        xs[idx] *= 2;
        System.out.println("arrCompound=" + xs[idx]);
        int p = a;
        p++;
        System.out.println("post=" + p);
    }
}
