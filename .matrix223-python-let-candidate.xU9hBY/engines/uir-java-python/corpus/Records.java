public class Records {
    record Point(int x, int y) {
        int sum() { return x + y; }
    }
    static class Holder {
        static int seen = 0;
        static int bump() { seen = seen + 1; return seen; }
    }
    enum Color { RED, GREEN }
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        Point p = new Point(a, a + 1);
        System.out.println(p.x() + "," + p.y() + "," + p.sum());
        System.out.println(p.toString());
        System.out.println(p.equals(new Point(a, a + 1)));
        System.out.println(Holder.bump() + "" + Holder.bump());
        String tb = """
            hello
              world
            """;
        System.out.print(tb);
    }
}
