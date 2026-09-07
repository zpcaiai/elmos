package {{packageName}}.verification;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Optional;
import java.util.UUID;

/**
 * Adds correlation metadata for differential observation without changing business behavior.
 */
public final class DifferentialCorrelationFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Elmos-Correlation-Id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String id = Optional.ofNullable(request.getHeader(HEADER))
                .filter(value -> !value.isBlank())
                .orElseGet(() -> UUID.randomUUID().toString());

        request.setAttribute(HEADER, id);
        response.setHeader(HEADER, id);
        filterChain.doFilter(request, response);
    }
}
