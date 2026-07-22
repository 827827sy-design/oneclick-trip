package com.oneclicktrip.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
public class InternalServiceAuthenticationFilter extends OncePerRequestFilter {
    public static final String HEADER_NAME = "X-Internal-Service-Key";

    private final byte[] expectedSecret;

    public InternalServiceAuthenticationFilter(
            @Value("${app.internal-service.secret}") String secret
    ) {
        this.expectedSecret = secret.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/internal/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String provided = request.getHeader(HEADER_NAME);
        boolean authenticated = provided != null && MessageDigest.isEqual(
                expectedSecret,
                provided.getBytes(StandardCharsets.UTF_8)
        );
        if (!authenticated) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"success\":false,\"message\":\"内部服务认证失败\",\"data\":null}"
            );
            return;
        }
        filterChain.doFilter(request, response);
    }
}
