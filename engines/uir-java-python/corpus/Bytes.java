// `var`, charsets and byte arrays.
//
// Two traps here, both found by this differential rather than by reading:
//   - Java bytes are *signed*, so a UTF-8 continuation byte 0xC3 is -61
//   - String.getBytes(Charset) never throws: characters the charset cannot
//     represent become '?', where Python's encode() raises
import java.nio.charset.StandardCharsets;

public class Bytes {

    record Tally(String label, int total) { }

    public static void main(String[] args) {
        String text = args[0];

        // `var` is not a type: it is whatever the initialiser is.  Every use
        // below needs the inferred type to resolve.
        var bytes = text.getBytes(StandardCharsets.UTF_8);
        var count = bytes.length;
        var label = "len=" + count;

        System.out.println(label);
        System.out.println("first=" + (count > 0 ? bytes[0] : 0));

        int sum = 0;
        for (var i = 0; i < bytes.length; i++) {
            sum += bytes[i];
        }
        System.out.println("sum=" + sum);

        var tally = new Tally(text, sum);
        System.out.println("tally=" + tally.label() + ":" + tally.total());

        var words = java.util.List.of("alpha", "beta");
        for (var w : words) {
            System.out.println("word=" + w.toUpperCase());
        }
        System.out.println("joined=" + words.stream().sorted().toList());

        // ASCII cannot represent every character, and Java replaces rather
        // than failing.
        var ascii = text.getBytes(StandardCharsets.US_ASCII);
        System.out.println("ascii_len=" + ascii.length);
        System.out.println("ascii_first=" + (ascii.length > 0 ? ascii[0] : 0));

        var latin = text.getBytes(StandardCharsets.ISO_8859_1);
        System.out.println("latin_len=" + latin.length);

        var wide = text.getBytes(StandardCharsets.UTF_16BE);
        System.out.println("wide_len=" + wide.length);

        // A checked exception the runtime now knows.
        try {
            throw new java.io.IOException("disk on fire");
        } catch (java.io.IOException e) {
            System.out.println("io=" + e.getMessage());
        }

        try {
            throw new SecurityException("denied");
        } catch (SecurityException e) {
            System.out.println("sec=" + e.getMessage());
        }
    }
}
