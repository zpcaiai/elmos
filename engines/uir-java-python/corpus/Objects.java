public class Objects {
    private int value;
    private static int created = 0;
    public static final int SCALE = 3;

    public Objects(int value) {
        this.value = value;
        created = created + 1;
    }
    public int scaled() { return this.value * SCALE; }
    public void bump(int by) { this.value += by; }
    public int getValue() { return value; }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        Objects one = new Objects(a);
        Objects two = new Objects(a + 1);
        one.bump(5);
        System.out.println("one=" + one.getValue());
        System.out.println("two=" + two.scaled());
        System.out.println("created=" + created);
        System.out.println("scale=" + SCALE);
        System.out.println("max=" + Integer.MAX_VALUE);
        System.out.println("min=" + Integer.MIN_VALUE);
    }
}
