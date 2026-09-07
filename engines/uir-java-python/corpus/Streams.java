// Streams and Optional.
//
// Java calls a stream ordered or unordered, and the distinction decides which
// operations mean anything: `set.stream().anyMatch(p)` gives the same answer
// whatever the iteration order, `set.stream().toList()` does not.  Everything
// below is drawn from a List or a LinkedHashSet, so all of it is ordered and all
// of it is comparable byte for byte.  The unordered cases are refused at
// translation time and are asserted by tests rather than printed here.
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class Streams {

    public static void main(String[] args) {
        int n = Integer.parseInt(args[0]);
        String needle = args[1];

        List<String> words = List.of("delta", "alpha", "charlie", "bravo", "alpha", "echo");

        System.out.println("count=" + words.stream().count());
        System.out.println("filtered=" + words.stream().filter(w -> w.length() > 4).toList());
        System.out.println("mapped=" + words.stream().map(w -> w.toUpperCase()).toList());
        System.out.println("distinct=" + words.stream().distinct().toList());
        System.out.println("sorted=" + words.stream().sorted().toList());
        System.out.println("limit=" + words.stream().limit(3).toList());
        System.out.println("skip=" + words.stream().skip(4).toList());
        System.out.println("any=" + words.stream().anyMatch(w -> w.equals(needle)));
        System.out.println("all=" + words.stream().allMatch(w -> w.length() > 3));
        System.out.println("none=" + words.stream().noneMatch(w -> w.isEmpty()));
        System.out.println("joined=" + words.stream().distinct().collect(Collectors.joining("|")));
        System.out.println("collected=" + words.stream().filter(w -> w.startsWith("a")).collect(Collectors.toList()));

        // Numbers, where the arithmetic still has to be Java's.  n is chosen to
        // overflow at the boundary vectors.
        List<Integer> numbers = List.of(n, n / 2, n - 1, 3);
        System.out.println("sum=" + numbers.stream().mapToInt(v -> v * 2).sum());
        System.out.println("reduced=" + numbers.stream().reduce(0, (x, y) -> x + y));
        System.out.println("biggest=" + numbers.stream().sorted().toList());

        // findFirst on an ordered stream is deterministic; on an unordered one
        // the emitter refuses it.
        Optional<String> first = words.stream().filter(w -> w.length() == 5).findFirst();
        System.out.println("present=" + first.isPresent());
        System.out.println("first=" + first.orElse("none"));
        System.out.println("mapped_opt=" + first.map(w -> w.length()).orElse(-1));

        Optional<String> missing = words.stream().filter(w -> w.equals("zzz")).findFirst();
        System.out.println("missing=" + missing.isPresent());
        System.out.println("fallback=" + missing.orElse("fallback"));
        try {
            System.out.println("never=" + missing.get());
        } catch (java.util.NoSuchElementException e) {
            System.out.println("threw=" + e.getMessage());
        }

        System.out.println("of=" + Optional.of("here").get());
        System.out.println("nullable=" + Optional.ofNullable(null).isPresent());
        System.out.println("empty=" + Optional.empty().isEmpty());

        // A LinkedHashSet has a specified iteration order, so a stream from it
        // is ordered and toList() is meaningful.
        LinkedHashSet<String> seen = new LinkedHashSet<>();
        seen.add("first");
        seen.add("second");
        seen.add("first");
        System.out.println("seen=" + seen.stream().toList());
        System.out.println("seen_upper=" + seen.stream().map(w -> w.toUpperCase()).toList());

        ArrayList<String> mutable = new ArrayList<>();
        mutable.add(needle);
        mutable.add("tail");
        System.out.println("mutable=" + mutable.stream().sorted().toList());
    }
}
