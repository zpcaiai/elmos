// Overloaded constructors.  Java picks one by the static types of the
// arguments; the translation dispatches on argument count, which is exact when
// (and only when) the arities differ.
public class Ctors {

    private int base;
    private int scale;
    private String label = "none";

    Ctors() {
        this.base = 1;
        this.scale = 1;
    }

    Ctors(int base) {
        this.base = base;
        this.scale = 2;
    }

    Ctors(int base, int scale) {
        this.base = base;
        this.scale = scale;
        this.label = "two";
    }

    int value() {
        return base * scale;
    }

    String describe() {
        return label + ":" + base + ":" + scale;
    }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);

        Ctors zero = new Ctors();
        Ctors one = new Ctors(a);
        Ctors two = new Ctors(a, a);

        System.out.println("zero=" + zero.value() + " " + zero.describe());
        System.out.println("one=" + one.value() + " " + one.describe());
        System.out.println("two=" + two.value() + " " + two.describe());

        // The field initialiser has to run before *every* constructor body, so
        // the no-arg case keeps the declared default.
        System.out.println("default_label=" + zero.describe());
    }
}
