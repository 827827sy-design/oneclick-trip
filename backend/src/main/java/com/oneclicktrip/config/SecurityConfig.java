package com.oneclicktrip.config;

import com.oneclicktrip.security.JwtAuthenticationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
public class SecurityConfig {
    /**
     * Spring Security 的总开关配置。
     *
     * 当前规则：
     * 1. 登录、健康检查、城市资料等公开接口不需要 token；
     * 2. 用户资料等接口需要登录；
     * 3. 每次请求都会先经过 JwtAuthenticationFilter，把 token 解析成当前用户。
     */
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http, JwtAuthenticationFilter jwtAuthenticationFilter) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/auth/**", "/api/health", "/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/cities/**", "/api/trip-templates/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/trip-plans/generate", "/api/ai/chat", "/api/ai/resume").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/trip-plans/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    /**
     * 密码编码器。
     *
     * data.sql 里的演示账号用了 {noop}123456，表示明文演示密码；
     * 新注册用户会使用这里的编码器自动生成带算法前缀的安全密码串。
     */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    /**
     * 允许前端 Vite 服务跨域访问后端。
     *
     * 开发时前端是 5173 端口，后端是 8080 端口，浏览器会认为它们是不同来源。
     */
    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOriginPatterns(List.of("*"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
