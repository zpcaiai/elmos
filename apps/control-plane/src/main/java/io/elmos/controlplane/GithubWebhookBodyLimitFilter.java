package io.elmos.controlplane;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.*;
import java.nio.charset.StandardCharsets;

final class GithubWebhookBodyLimitFilter extends OncePerRequestFilter {
    private final int maxBodyBytes;
    GithubWebhookBodyLimitFilter(int maxBodyBytes) { this.maxBodyBytes = maxBodyBytes; }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        byte[] body = request.getInputStream().readNBytes(maxBodyBytes + 1);
        if (body.length > maxBodyBytes) { response.sendError(HttpServletResponse.SC_REQUEST_ENTITY_TOO_LARGE); return; }
        chain.doFilter(new RawBodyRequest(request, body), response);
    }

    private static final class RawBodyRequest extends HttpServletRequestWrapper {
        private final byte[] body;
        RawBodyRequest(HttpServletRequest request, byte[] body) { super(request); this.body = body; }
        @Override public int getContentLength() { return body.length; }
        @Override public long getContentLengthLong() { return body.length; }
        @Override public BufferedReader getReader() { return new BufferedReader(new InputStreamReader(new ByteArrayInputStream(body), StandardCharsets.UTF_8)); }
        @Override public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override public boolean isFinished() { return input.available() == 0; }
                @Override public boolean isReady() { return true; }
                @Override public void setReadListener(ReadListener listener) { throw new UnsupportedOperationException("async reads are not supported"); }
                @Override public int read() { return input.read(); }
                @Override public int read(byte[] bytes, int offset, int length) { return input.read(bytes, offset, length); }
            };
        }
    }
}
