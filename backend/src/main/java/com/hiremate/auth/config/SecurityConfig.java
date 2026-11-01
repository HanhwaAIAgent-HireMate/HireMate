package com.hiremate.auth.config;

import com.hiremate.auth.application.MemberAuthenticationProvider;
import com.hiremate.auth.application.MemberUserDetailsService;
import com.hiremate.global.ProblemResponses;
import jakarta.servlet.DispatcherType;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    /** 면접관에게 여는 읽기 경로. 그 밖의 업무 경로는 HR만 쓴다 (InterviewerAccessTests가 목록을 검사한다). */
    static final String[] INTERVIEWER_READS = {
        "/api/companies/me/profile",
        "/api/stages/{stageId}",
        "/api/stages/{stageId}/candidates",
        "/api/stages/{stageId}/candidates/{applicationId}",
        "/api/stages/{stageId}/candidates/{applicationId}/history",
        "/api/stages/{stageId}/candidates/{applicationId}/analysis",
        "/api/stages/{stageId}/candidates/{applicationId}/profile",
        "/api/stages/{stageId}/assessment/results/{applicationId}",
        "/api/stages/{stageId}/assessment/results/{applicationId}/file",
        "/api/recruitments/{recruitmentId}/applications/{applicationId}/documents/{type}",
        "/api/stages/{stageId}/candidates/{applicationId}/interview",
        "/api/stages/{stageId}/candidates/{applicationId}/interview/preparing",
        "/api/stages/{stageId}/interviewers",
    };

    @Bean
    PasswordEncoder passwordEncoder() {
        Pbkdf2PasswordEncoder pbkdf2 = new Pbkdf2PasswordEncoder("", 16, 600_000,
                Pbkdf2PasswordEncoder.SecretKeyFactoryAlgorithm.PBKDF2WithHmacSHA256);
        String id = "pbkdf2-hmac-sha256-600000";
        return new DelegatingPasswordEncoder(id, Map.of(id, pbkdf2));
    }

    @Bean
    AuthenticationManager authenticationManager(MemberUserDetailsService members, PasswordEncoder passwords) {
        return new ProviderManager(new MemberAuthenticationProvider(members, passwords));
    }

    @Bean
    HttpSessionCsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(), new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(HttpSessionCsrfTokenRepository csrfTokens) {
        CsrfAuthenticationStrategy csrf = new CsrfAuthenticationStrategy(csrfTokens);
        csrf.setRequestHandler(new CsrfTokenRequestAttributeHandler());
        return new CompositeSessionAuthenticationStrategy(List.of(new ChangeSessionIdAuthenticationStrategy(), csrf));
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, SecurityContextRepository contexts,
            HttpSessionCsrfTokenRepository csrfTokens, SessionAuthenticationStrategy sessionStrategy,
            ProblemResponses problems, InterviewerAccess interviewerAccess) throws Exception {
        return http
                .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens)
                        .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()))
                .securityContext(context -> context.securityContextRepository(contexts).requireExplicitSave(true))
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                        .sessionAuthenticationStrategy(sessionStrategy))
                .requestCache(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, exception) -> problems.write(
                                response, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "Authentication is required."))
                        .accessDeniedHandler((request, response, exception) -> problems.write(response,
                                HttpStatus.FORBIDDEN, exception instanceof CsrfException ? "INVALID_CSRF" : "FORBIDDEN",
                                "Access is denied.")))
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/csrf", "/actuator/health").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/signup", "/api/auth/login", "/api/auth/logout")
                        .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/me").authenticated()
                        // 면접관 모드: 로그인한 계정이 지정된 면접 전형 목록
                        .requestMatchers(HttpMethod.GET, "/api/interviewer/**").authenticated()
                        // 지원자용 채용 페이지와 지원서 제출. 로그인 없이 쓰며 POST는 CSRF 토큰이 필요하다
                        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/public/**").permitAll()
                        // 면접관 모드: 지정된 면접 전형(과 그 채용)의 자료 읽기. HR은 그대로 통과한다
                        .requestMatchers(HttpMethod.GET, INTERVIEWER_READS).access(interviewerAccess)
                        .requestMatchers("/api/companies", "/api/companies/**", "/api/recruitments",
                                "/api/recruitments/**", "/api/stages", "/api/stages/**").hasRole("HR")
                        .requestMatchers(HttpMethod.GET, "/v3/api-docs", "/v3/api-docs/**", "/swagger-ui.html",
                                "/swagger-ui/**").hasRole("HR")
                        .anyRequest().denyAll())
                .logout(logout -> logout.logoutUrl("/api/auth/logout")
                        .deleteCookies("SESSION")
                        .logoutSuccessHandler((request, response, authentication) -> response.setStatus(204)))
                .build();
    }
}
