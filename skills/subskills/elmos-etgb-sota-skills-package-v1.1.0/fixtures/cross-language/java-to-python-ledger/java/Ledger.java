import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Ledger {
    private final Map<String, BigDecimal> balances = new LinkedHashMap<>();
    private final List<String> history = new ArrayList<>();

    public Ledger() {
        balances.put("A", money("100.00"));
        balances.put("B", money("25.50"));
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value).setScale(2, RoundingMode.UNNECESSARY);
    }

    public void transfer(String from, String to, String value) {
        BigDecimal amount = money(value);
        BigDecimal source = balances.get(from);
        if (amount.signum() <= 0) throw new IllegalArgumentException("INVALID_AMOUNT");
        if (source.compareTo(amount) < 0) throw new IllegalStateException("INSUFFICIENT_FUNDS");
        balances.put(from, source.subtract(amount));
        balances.put(to, balances.get(to).add(amount));
        history.add(from + "->" + to + ":" + amount.toPlainString());
    }

    public void deposit(String account, String value) {
        BigDecimal amount = money(value);
        balances.put(account, balances.get(account).add(amount));
        history.add("deposit:" + account + ":" + amount.toPlainString());
    }

    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    public String asJson(String error) {
        BigDecimal total = balances.values().stream().reduce(BigDecimal.ZERO, BigDecimal::add).setScale(2);
        return "{" +
            "\"balances\":{\"A\":" + quote(balances.get("A").toPlainString()) + ",\"B\":" + quote(balances.get("B").toPlainString()) + "}," +
            "\"error\":" + quote(error) + "," +
            "\"history\":[" + quote(history.get(0)) + "," + quote(history.get(1)) + "]," +
            "\"total\":" + quote(total.toPlainString()) +
            "}";
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        ledger.transfer("A", "B", "12.35");
        ledger.deposit("B", "0.10");
        String error = "";
        try {
            ledger.transfer("A", "B", "1000.00");
        } catch (IllegalStateException ex) {
            error = ex.getMessage();
        }
        System.out.println(ledger.asJson(error));
    }
}
