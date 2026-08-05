// String.matches, over the subset of the regex dialects where Java and Python
// actually agree.
//
// They look identical and are not.  Three of the differences are silent, and all
// three are exercised below:
//   - `.` excludes five line terminators in Java, only \n in Python
//   - \d \w \s \b are ASCII-only in Java by default, Unicode-aware in Python
//   - matches() is anchored at both ends whether or not the pattern says so
// The arguments include an Arabic-Indic digit string and a string with a
// trailing newline for exactly that reason.
public class Regex {

    public static void main(String[] args) {
        String s = args[0];

        // The shapes that actually occur: hashes, ids, versions.
        System.out.println("hex64=" + s.matches("[0-9a-f]{64}"));
        System.out.println("hex40=" + s.matches("[0-9a-f]{40}"));
        System.out.println("prefixed=" + s.matches("sha256:[0-9a-f]{64}"));
        System.out.println("anchored=" + s.matches("^[0-9a-f]{64}$"));
        System.out.println("id=" + s.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"));
        System.out.println("uuid=" + s.matches("[0-9a-fA-F-]{36}"));
        System.out.println("upper=" + s.matches("[A-Z0-9_]{3,80}"));

        // Predefined classes: ASCII-only on the Java side.
        System.out.println("digits=" + s.matches("\\d{6}"));
        System.out.println("word=" + s.matches("\\w+"));
        System.out.println("space=" + s.matches("\\s+"));
        System.out.println("nondigit=" + s.matches("\\D+"));

        // `.` and the line terminators.
        System.out.println("dot=" + s.matches("a.c"));
        System.out.println("dotstar=" + s.matches(".*"));
        System.out.println("dotplus=" + s.matches(".+"));

        // Groups, alternation, optional groups, reluctant quantifiers.
        System.out.println("ref=" + s.matches("(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+"));
        System.out.println("host=" + s.matches("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"));
        System.out.println("lazy=" + s.matches("a.*?c"));
        System.out.println("phone=" + s.matches("^1[3-9]\\d{9}$"));
        System.out.println("escaped=" + s.matches("\\$\\{[^}]+}"));

        // matches() is whole-string, so an unanchored pattern still has to
        // cover everything.
        System.out.println("partial=" + s.matches("abc"));
        System.out.println("empty=" + s.matches(""));

        // Lookahead is spelled the same in both dialects.
        System.out.println("ahead=" + s.matches("(?=.*[0-9])[A-Za-z0-9]+"));
    }
}
