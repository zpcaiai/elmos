package {{packageName}}.legacycompat;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.ModelAndView;

import java.io.IOException;
import java.util.Objects;

/**
 * Generated only when NavigationDispatchIR cannot be represented safely by a plain controller return value.
 * Contains framework semantics, never business logic.
 */
public final class LegacyNavigationResolver {

    public enum Kind { RENDER, FORWARD, INCLUDE, REDIRECT, ERROR_DISPATCH, STREAM, NONE }

    public record Navigation(
            Kind kind,
            String target,
            Integer status,
            boolean contextRelative,
            String legacyRouteId) {}

    public ModelAndView resolve(
            Navigation navigation,
            HttpServletRequest request,
            HttpServletResponse response) throws IOException, ServletException {

        Objects.requireNonNull(navigation, "navigation");
        return switch (navigation.kind()) {
            case RENDER -> new ModelAndView(navigation.target());
            case FORWARD -> new ModelAndView("forward:" + navigation.target());
            case REDIRECT -> {
                if (navigation.status() != null) {
                    response.setStatus(navigation.status());
                }
                yield new ModelAndView("redirect:" + navigation.target());
            }
            case INCLUDE -> {
                RequestDispatcher dispatcher = request.getRequestDispatcher(navigation.target());
                dispatcher.include(request, response);
                yield null;
            }
            case ERROR_DISPATCH -> {
                RequestDispatcher dispatcher = request.getRequestDispatcher(navigation.target());
                dispatcher.forward(request, response);
                yield null;
            }
            case STREAM, NONE -> null;
        };
    }
}
