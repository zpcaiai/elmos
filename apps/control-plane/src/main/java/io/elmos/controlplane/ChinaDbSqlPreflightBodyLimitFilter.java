package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/** Rejects oversized SQL envelopes before controller deserialization. */
final class ChinaDbSqlPreflightBodyLimitFilter extends OncePerRequestFilter {
    private final ObjectMapper json;

    ChinaDbSqlPreflightBodyLimitFilter(ObjectMapper json) {
        this.json = json;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        if (!"POST".equals(request.getMethod())) {
            chain.doFilter(request, response);
            return;
        }
        String mediaType = request.getContentType() == null
                ? "" : request.getContentType().split(";", 2)[0].trim();
        String contentEncoding = request.getHeader("Content-Encoding");
        if (!"application/json".equalsIgnoreCase(mediaType)
                || (contentEncoding != null && !"identity".equalsIgnoreCase(contentEncoding.trim()))
                || request.getHeader("Transfer-Encoding") != null) {
            writeFailure(response, new ChinaDbSqlPreflightFailure(
                    ChinaDbSqlPreflightFailure.Kind.REQUEST_REJECTED));
            return;
        }
        byte[] body = request.getInputStream().readNBytes(ChinaDbSqlPreflightProtocol.MAX_REQUEST_BYTES + 1);
        if (body.length > ChinaDbSqlPreflightProtocol.MAX_REQUEST_BYTES) {
            writeFailure(response, new ChinaDbSqlPreflightFailure(
                    ChinaDbSqlPreflightFailure.Kind.REQUEST_TOO_LARGE));
            return;
        }
        long declared = request.getContentLengthLong();
        if (declared >= 0 && declared != body.length) {
            writeFailure(response, new ChinaDbSqlPreflightFailure(
                    ChinaDbSqlPreflightFailure.Kind.REQUEST_REJECTED));
            return;
        }
        chain.doFilter(new ReplayableRequest(request, body), response);
    }

    private void writeFailure(
            HttpServletResponse response,
            ChinaDbSqlPreflightFailure failure
    ) throws IOException {
        response.setStatus(failure.status().value());
        response.setContentType("application/json");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "private, no-store");
        json.writeValue(response.getOutputStream(), failure.body());
    }

    private static final class ReplayableRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        ReplayableRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override public int getContentLength() { return body.length; }
        @Override public long getContentLengthLong() { return body.length; }
        @Override public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }
        @Override public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override public boolean isFinished() { return input.available() == 0; }
                @Override public boolean isReady() { return true; }
                @Override public void setReadListener(ReadListener listener) {
                    throw new UnsupportedOperationException("async reads are not supported");
                }
                @Override public int read() { return input.read(); }
                @Override public int read(byte[] bytes, int offset, int length) {
                    return input.read(bytes, offset, length);
                }
            };
        }
    }
}
