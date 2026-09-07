import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneOffset;
import java.time.Clock;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.DateTimeException;
import java.time.temporal.ChronoUnit;

public class Times {
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);

        // ---- Instant: nanosecond precision, which Python's datetime lacks --
        Instant epoch = Instant.EPOCH;
        System.out.println("epoch=" + epoch);
        System.out.println("nano=" + Instant.ofEpochSecond(0, 1));
        System.out.println("milli=" + Instant.ofEpochSecond(0, 100000000));
        System.out.println("micro=" + Instant.ofEpochSecond(0, 100200000));
        System.out.println("full=" + Instant.ofEpochSecond(0, 123456789));
        System.out.println("neg=" + Instant.ofEpochSecond(-1));
        Instant t = Instant.ofEpochSecond(a);
        System.out.println("t=" + t + " sec=" + t.getEpochSecond() + " ms=" + t.toEpochMilli());
        System.out.println("plus=" + t.plusSeconds(90).plusNanos(5));

        // ---- Duration: its own toString spelling ---------------------------
        System.out.println("zero=" + Duration.ZERO);
        System.out.println("d1=" + Duration.ofSeconds(-1));
        System.out.println("d2=" + Duration.ofSeconds(2 * 3600 + 3 * 60 + 4, 500000000));
        System.out.println("d3=" + Duration.ofHours(1));
        System.out.println("d4=" + Duration.ofMillis(1500));
        System.out.println("d5=" + Duration.ofDays(2));
        Duration span = Duration.between(epoch, t);
        System.out.println("span=" + span + " ms=" + span.toMillis() + " neg=" + span.isNegative());
        System.out.println("mult=" + span.multipliedBy(3) + " negd=" + span.negated());

        // ---- LocalDate: month arithmetic clamps the day --------------------
        LocalDate jan31 = LocalDate.of(2021, 1, 31);
        System.out.println("clamp=" + jan31.plusMonths(1));
        System.out.println("clampLeap=" + LocalDate.of(2020, 1, 31).plusMonths(1));
        System.out.println("year=" + LocalDate.of(2024, 2, 29).plusYears(1));
        System.out.println("epochDay=" + jan31.toEpochDay() + " leap=" + jan31.isLeapYear());
        System.out.println("len=" + LocalDate.of(2024, 2, 1).lengthOfMonth());
        // Outside the range Python's date can represent at all.
        System.out.println("far=" + LocalDate.of(12345, 6, 7));
        System.out.println("ancient=" + LocalDate.of(-44, 3, 15));
        System.out.println("shift=" + LocalDate.of(2020, 3, 1).plusDays(a % 400));

        // ---- LocalTime / LocalDateTime: seconds omitted when zero ----------
        System.out.println("lt=" + LocalTime.of(10, 0));
        System.out.println("lts=" + LocalTime.of(10, 0, 5));
        System.out.println("ldt=" + LocalDateTime.of(2020, 1, 2, 3, 4));
        LocalDateTime ldt = LocalDateTime.of(2020, 1, 2, 3, 4, 5);
        System.out.println("ldts=" + ldt + " es=" + ldt.toEpochSecond(ZoneOffset.UTC));
        System.out.println("toInstant=" + ldt.toInstant(ZoneOffset.UTC));

        // ---- ZoneOffset ----------------------------------------------------
        System.out.println("utc=" + ZoneOffset.UTC + " plus8=" + ZoneOffset.ofHours(8));
        System.out.println("half=" + ZoneOffset.ofHoursMinutes(5, 30));

        // ---- ChronoUnit truncates toward zero ------------------------------
        System.out.println("days=" + ChronoUnit.DAYS.between(
                LocalDate.of(2020, 1, 1), LocalDate.of(2021, 3, 15)));
        System.out.println("months=" + ChronoUnit.MONTHS.between(
                LocalDate.of(2020, 1, 31), LocalDate.of(2020, 3, 30)));
        System.out.println("hours=" + ChronoUnit.HOURS.between(
                epoch, Instant.ofEpochSecond(3600 * 5 - 1)));
        System.out.println("backwards=" + ChronoUnit.DAYS.between(
                LocalDate.of(2021, 1, 1), LocalDate.of(2020, 1, 1)));
        // Negative deltas are where truncation differs from flooring.
        System.out.println("negHours=" + ChronoUnit.HOURS.between(
                Instant.ofEpochSecond(3600 * 5 - 1), epoch));
        System.out.println("negMinutes=" + ChronoUnit.MINUTES.between(
                Instant.ofEpochSecond(-90), epoch));
        System.out.println("negSeconds=" + ChronoUnit.SECONDS.between(
                Instant.ofEpochSecond(0, 500000000), Instant.ofEpochSecond(-2)));

        // ---- Clock ---------------------------------------------------------
        Clock fixed = Clock.fixed(Instant.ofEpochSecond(1000, 500), ZoneOffset.UTC);
        System.out.println("clock=" + fixed.instant() + " ms=" + fixed.millis());

        // ---- formatter -----------------------------------------------------
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        System.out.println("fmt=" + fmt.format(ldt));

        // ---- parsing and its failures --------------------------------------
        System.out.println("parsed=" + Instant.parse("2020-01-02T03:04:05.123Z"));
        System.out.println("parsedDate=" + LocalDate.parse("2020-02-29"));
        try {
            Instant.parse("not-a-time");
        } catch (DateTimeParseException e) {
            System.out.println("parseFailed");
        }
        try {
            LocalDate.of(2021, 2, 29);
        } catch (DateTimeException e) {
            System.out.println("invalidDate=" + e.getMessage());
        }
        try {
            LocalTime.of(24, 0);
        } catch (DateTimeException e) {
            System.out.println("invalidTime=" + e.getMessage());
        }
    }
}
