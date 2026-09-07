package io.elmos.legacy.web;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public class RequestAuditInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        response.setHeader("X-Legacy-Audit", request.getMethod() + " " + request.getRequestURI());
        return true;
    }
}
