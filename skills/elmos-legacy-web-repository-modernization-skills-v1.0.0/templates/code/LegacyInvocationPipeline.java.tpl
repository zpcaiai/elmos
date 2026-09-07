package {{packageName}}.legacycompat;

import java.util.List;
import java.util.Objects;

/**
 * Represents an ordered around-invocation chain for custom Struts2/RequestProcessor semantics.
 * The generated pipeline is used only when native Spring extension points cannot preserve order/short-circuit.
 */
public final class LegacyInvocationPipeline<C, R> {

    @FunctionalInterface
    public interface Terminal<C, R> {
        R invoke(C context) throws Exception;
    }

    @FunctionalInterface
    public interface Step<C, R> {
        R invoke(C context, Chain<C, R> chain) throws Exception;
    }

    public interface Chain<C, R> {
        R proceed(C context) throws Exception;
    }

    private final List<Step<C, R>> steps;
    private final Terminal<C, R> terminal;

    public LegacyInvocationPipeline(List<Step<C, R>> steps, Terminal<C, R> terminal) {
        this.steps = List.copyOf(steps);
        this.terminal = Objects.requireNonNull(terminal);
    }

    public R invoke(C context) throws Exception {
        return new Cursor(0).proceed(context);
    }

    private final class Cursor implements Chain<C, R> {
        private final int index;

        private Cursor(int index) {
            this.index = index;
        }

        @Override
        public R proceed(C context) throws Exception {
            if (index >= steps.size()) {
                return terminal.invoke(context);
            }
            return steps.get(index).invoke(context, new Cursor(index + 1));
        }
    }
}
