// Maps and sets.  The whole design of this translation turns on one line in the
// javadoc: `Map.of` and `Set.of` leave iteration order *unspecified* and
// randomise it per JVM run.  So every observation here is either
// order-independent (and exact), or made on a LinkedHashMap/TreeMap whose order
// Java does specify.  Printing a Map.of is refused at translation time; there is
// no output below that could prove it, which is the point.
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.HashMap;
import java.util.TreeMap;
import java.util.TreeSet;

public class Maps {

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        String key = args[1];

        // --- immutable factories, order-independent observations ----------
        Map<String, Integer> fixed = Map.of("a", 1, "b", 2, "c", 3);
        System.out.println("size=" + fixed.size());
        System.out.println("get_a=" + fixed.get("a"));
        System.out.println("get_missing=" + fixed.get("zz"));
        System.out.println("default=" + fixed.getOrDefault("zz", -1));
        System.out.println("hasKey=" + fixed.containsKey(key));
        System.out.println("hasValue=" + fixed.containsValue(a));
        System.out.println("empty=" + fixed.isEmpty());

        // Map.equals compares entry sets, not order.
        System.out.println("eq=" + fixed.equals(Map.of("c", 3, "b", 2, "a", 1)));
        System.out.println("neq=" + fixed.equals(Map.of("a", 1)));

        // Immutability is part of the contract, and a plain dict would not have it.
        try {
            fixed.put("d", 4);
            System.out.println("mutated");
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable");
        }

        // Map.of rejects duplicate keys and nulls.
        try {
            Map<String, Integer> bad = Map.of("x", 1, "x", 2);
            System.out.println("dup ok " + bad.size());
        } catch (IllegalArgumentException e) {
            System.out.println("dup=" + e.getMessage());
        }

        // --- mutable maps -------------------------------------------------
        Map<String, Integer> counts = new HashMap<>();
        System.out.println("put_new=" + counts.put(key, a));
        System.out.println("put_again=" + counts.put(key, a + 1));
        System.out.println("read=" + counts.get(key));
        System.out.println("absent=" + counts.putIfAbsent(key, 99));
        System.out.println("absent_new=" + counts.putIfAbsent("other", 5));
        System.out.println("removed=" + counts.remove(key));
        System.out.println("size_after=" + counts.size());

        // --- ordered maps: iteration is allowed because Java specifies it --
        LinkedHashMap<String, Integer> ordered = new LinkedHashMap<>();
        ordered.put("z", a);
        ordered.put("y", a * 2);
        ordered.put("x", a * 3);
        for (String k : ordered.keySet()) {
            System.out.println("ordered " + k + "=" + ordered.get(k));
        }
        System.out.println("ordered_str=" + ordered.toString());

        TreeMap<String, Integer> sorted = new TreeMap<>();
        sorted.put("m", 1);
        sorted.put("a", 2);
        sorted.put("z", 3);
        System.out.println("sorted_str=" + sorted.toString());

        // --- sets -----------------------------------------------------------
        Set<String> tags = Set.of("p", "q", "r");
        System.out.println("set_size=" + tags.size());
        System.out.println("set_has=" + tags.contains(key));
        System.out.println("set_eq=" + tags.equals(Set.of("r", "q", "p")));

        LinkedHashSet<String> seen = new LinkedHashSet<>();
        System.out.println("added=" + seen.add("first"));
        System.out.println("again=" + seen.add("first"));
        seen.add("second");
        System.out.println("seen=" + seen.toString());

        TreeSet<String> ranked = new TreeSet<>();
        ranked.add("gamma");
        ranked.add("alpha");
        ranked.add("beta");
        System.out.println("ranked=" + ranked.toString());

        // --- key equality is Java's, not Python's ---------------------------
        // In Python `True == 1` and `1.0 == 1`; in Java a Boolean key and an
        // Integer key are never equal, and neither are Integer and Double.
        Map<Object, String> mixed = new LinkedHashMap<>();
        mixed.put(1, "int");
        mixed.put(Boolean.TRUE, "bool");
        mixed.put(1.0, "double");
        System.out.println("mixed_size=" + mixed.size());
        System.out.println("mixed_int=" + mixed.get(1));
        System.out.println("mixed_bool=" + mixed.get(Boolean.TRUE));
    }
}
