package com.hiremate;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.MemberRole;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthIntegrationTests {

    private static final String PASSWORD = "test-password-2026";

    @LocalServerPort
    private int port;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private SessionRepository<? extends Session> sessions;

    @Autowired
    private RedisConnectionFactory redis;

    private final JsonMapper mapper = new JsonMapper();

    @Test
    void publicCsrfCreatesTokenAndSafeSessionCookie() throws Exception {
        HttpResponse<String> response = send(client(), "GET", "/api/auth/csrf", null, null);
        assertThat(response.statusCode()).isEqualTo(200);
        JsonNode token = json(response);
        assertThat(token.path("token").asString()).isNotBlank();
        assertThat(token.path("headerName").asString()).isEqualTo("X-CSRF-TOKEN");
        assertThat(token.path("parameterName").asString()).isEqualTo("_csrf");
        assertThat(response.headers().allValues("Set-Cookie"))
                .anySatisfy(cookie -> assertThat(cookie).contains("SESSION=", "HttpOnly", "SameSite=Lax"));
    }

    @Test
    void forwardedHttpsProducesSecureSessionCookie() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri("/api/auth/csrf"))
                .header("X-Forwarded-Proto", "https")
                .GET().build();
        HttpResponse<String> response = client().send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().allValues("Set-Cookie"))
                .anySatisfy(cookie -> assertThat(cookie).contains("Secure", "HttpOnly", "SameSite=Lax"));
    }

    @Test
    void anonymousBusinessAndUnknownPathsAreDenied() throws Exception {
        HttpClient client = client();
        for (String path : List.of("/api/auth/me", "/api/companies", "/api/companies/123", "/api/recruitments",
                "/api/stages/123", "/unregistered", "/careers/123", "/api/ai/123", "/v3/api-docs")) {
            assertProblem(send(client, "GET", path, null, null), 401, "UNAUTHENTICATED");
        }
    }

    @Test
    void unsafePublicRequestsRequireCsrf() throws Exception {
        HttpClient client = client();
        assertProblem(send(client, "POST", "/api/auth/signup", "{}", null), 403, "INVALID_CSRF");
        assertProblem(send(client, "POST", "/api/auth/login", "{}", null), 403, "INVALID_CSRF");
    }

    @Test
    void healthRemainsPublicButOtherMethodsAreNotPublic() throws Exception {
        HttpClient client = client();
        assertThat(send(client, "GET", "/actuator/health", null, null).statusCode()).isEqualTo(200);
        String token = csrf(client);
        for (String path : List.of("/actuator/health", "/api/auth/csrf", "/api/auth/me")) {
            assertProblem(send(client, "POST", path, "{}", token), 401, "UNAUTHENTICATED");
        }
        assertProblem(send(client, "GET", "/api/auth/login", null, null), 401, "UNAUTHENTICATED");
        assertProblem(send(client, "GET", "/api/auth/signup", null, null), 401, "UNAUTHENTICATED");
        assertProblem(send(client, "GET", "/api/auth/logout", null, null), 401, "UNAUTHENTICATED");
    }

    @Test
    void signupCreatesNormalizedHrAndCompanyWithoutLoggingIn() throws Exception {
        HttpClient client = client();
        String email = email();
        HttpResponse<String> response = signup(client, "  " + email.toUpperCase(java.util.Locale.ROOT) + "  ");
        assertThat(response.statusCode()).isEqualTo(201);
        JsonNode member = json(response);
        assertThat(member.path("email").asString()).isEqualTo(email);
        assertThat(member.path("role").asString()).isEqualTo("HR");
        assertThat(UUID.fromString(member.path("companyId").asString())).isNotNull();
        assertThat(UUID.fromString(member.path("memberId").asString())).isNotNull();
        assertThat(jdbc.queryForObject("SELECT name FROM companies WHERE id = ?", String.class,
                UUID.fromString(member.path("companyId").asString()))).isEqualTo("Test company");
        String hash = jdbc.queryForObject("SELECT password_hash FROM members WHERE email = ?", String.class, email);
        assertThat(hash).startsWith("{pbkdf2-hmac-sha256-600000}").doesNotContain(PASSWORD);
        assertThat(member.propertyNames())
                .containsExactlyInAnyOrder("memberId", "companyId", "name", "email", "role");
        assertProblem(send(client, "GET", "/api/auth/me", null, null), 401, "UNAUTHENTICATED");
    }

    @Test
    void duplicateEmailDoesNotCreateAnotherCompany() throws Exception {
        String email = email();
        HttpClient client = client();
        assertThat(signup(client, email).statusCode()).isEqualTo(201);
        long count = companyCount();
        assertProblem(signup(client, email.toUpperCase(java.util.Locale.ROOT)), 409, "EMAIL_ALREADY_EXISTS");
        assertThat(companyCount()).isEqualTo(count);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM members WHERE email = ?", Long.class, email)).isEqualTo(1);
    }

    @Test
    void concurrentDuplicateSignupRollsBackLosingCompany() throws Exception {
        String email = email();
        HttpClient first = client();
        HttpClient second = client();
        String firstToken = csrf(first);
        String secondToken = csrf(second);
        long companies = companyCount();
        String body = signupBody(email, PASSWORD);
        CompletableFuture<HttpResponse<String>> one = first.sendAsync(
                request("POST", "/api/auth/signup", body, firstToken), HttpResponse.BodyHandlers.ofString());
        CompletableFuture<HttpResponse<String>> two = second.sendAsync(
                request("POST", "/api/auth/signup", body, secondToken), HttpResponse.BodyHandlers.ofString());
        assertThat(List.of(one.join().statusCode(), two.join().statusCode())).containsExactlyInAnyOrder(201, 409);
        assertThat(companyCount()).isEqualTo(companies + 1);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM members WHERE email = ?", Long.class, email)).isEqualTo(1);
    }

    @Test
    void roleAndCompanyOverpostingCannotChangeSignupAuthority() throws Exception {
        HttpClient client = client();
        JsonNode existing = json(signup(client, email()));
        UUID suppliedCompany = UUID.fromString(existing.path("companyId").asString());
        String body = mapper.writeValueAsString(Map.of("companyName", "New company", "name", "Test HR",
                "email", email(), "password", PASSWORD, "role", "INTERVIEWER", "companyId", suppliedCompany));
        HttpResponse<String> response = send(client, "POST", "/api/auth/signup", body, csrf(client));
        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(json(response).path("role").asString()).isEqualTo("HR");
        assertThat(json(response).path("companyId").asString()).isNotEqualTo(suppliedCompany.toString());
    }

    @Test
    void loginChangesSessionIdAndRestoresDbPrincipalOnNextRequest() throws Exception {
        HttpClient client = client();
        String email = email();
        JsonNode registered = json(signup(client, email));
        String token = csrf(client);
        String oldCookie = cookie(client);
        HttpResponse<String> login = login(client,
                "  " + email.toUpperCase(java.util.Locale.ROOT) + "  ", PASSWORD, token);
        assertThat(login.statusCode()).isEqualTo(200);
        assertThat(cookie(client)).isNotEqualTo(oldCookie);
        HttpResponse<String> me = send(client, "GET", "/api/auth/me", null, null);
        assertThat(me.statusCode()).isEqualTo(200);
        assertThat(json(me)).isEqualTo(registered);
        assertThat(login.body()).doesNotContain("password", "passwordHash", "password_hash", "sessionId");
        assertThat(json(me).propertyNames())
                .containsExactlyInAnyOrder("memberId", "companyId", "name", "email", "role");
        assertProblem(withCookie("GET", "/api/auth/me", oldCookie), 401, "UNAUTHENTICATED");
    }

    @Test
    void absentAccountAndWrongPasswordHaveSameGenericError() throws Exception {
        String email = email();
        HttpClient client = client();
        signup(client, email);
        HttpResponse<String> wrong = login(client, email, "test-wrong-password", csrf(client));
        HttpResponse<String> absent = login(client, email(), "test-wrong-password", csrf(client));
        assertProblem(wrong, 401, "INVALID_CREDENTIALS");
        assertProblem(absent, 401, "INVALID_CREDENTIALS");
        assertThat(json(wrong).path("detail")).isEqualTo(json(absent).path("detail"));
        assertThat(wrong.body()).doesNotContain(email, "test-wrong-password", "password_hash", "SQLException");
    }

    @Test
    void missingAndOldCsrfCannotLogoutButRotatedTokenCan() throws Exception {
        HttpClient client = client();
        String email = email();
        signup(client, email);
        String beforeLogin = csrf(client);
        assertThat(login(client, email, PASSWORD, beforeLogin).statusCode()).isEqualTo(200);
        String loggedInCookie = cookie(client);
        assertProblem(send(client, "POST", "/api/auth/logout", null, null), 403, "INVALID_CSRF");
        assertThat(send(client, "GET", "/api/auth/me", null, null).statusCode()).isEqualTo(200);
        assertProblem(send(client, "POST", "/api/auth/logout", null, beforeLogin), 403, "INVALID_CSRF");
        assertThat(send(client, "GET", "/api/auth/me", null, null).statusCode()).isEqualTo(200);
        String afterLogin = csrf(client);
        assertThat(afterLogin).isNotEqualTo(beforeLogin);
        HttpResponse<String> logout = send(client, "POST", "/api/auth/logout", null, afterLogin);
        assertThat(logout.statusCode()).isEqualTo(204);
        assertThat(logout.headers().allValues("Set-Cookie"))
                .anySatisfy(value -> assertThat(value).contains("SESSION=", "Max-Age=0"));
        assertProblem(withCookie("GET", "/api/auth/me", loggedInCookie), 401, "UNAUTHENTICATED");
        assertProblem(send(client, "GET", "/api/auth/me", null, null), 401, "UNAUTHENTICATED");
    }

    @Test
    void interviewerCanLoginButCannotEnterHrRoutes() throws Exception {
        HttpClient client = client();
        String email = email();
        signup(client, email);
        jdbc.update("UPDATE members SET role = 'INTERVIEWER' WHERE email = ?", email);
        assertThat(login(client, email, PASSWORD, csrf(client)).statusCode()).isEqualTo(200);
        assertThat(json(send(client, "GET", "/api/auth/me", null, null)).path("role").asString())
                .isEqualTo("INTERVIEWER");
        for (String path : List.of("/api/companies", "/api/recruitments/1", "/api/stages/1", "/v3/api-docs",
                "/swagger-ui.html")) {
            assertProblem(send(client, "GET", path, null, null), 403, "FORBIDDEN");
        }
        assertThat(send(client, "POST", "/api/auth/logout", null, csrf(client)).statusCode()).isEqualTo(204);
    }

    @Test
    void hrEntersKnownBusinessPrefixesButUnknownCareersAndAiRemainClosed() throws Exception {
        HttpClient client = client();
        String email = email();
        signup(client, email);
        login(client, email, PASSWORD, csrf(client));
        for (String path : List.of("/api/companies", "/api/companies/1", "/api/recruitments/1/unknown",
                "/api/stages/1")) {
            assertThat(send(client, "GET", path, null, null).statusCode()).isEqualTo(404);
        }
        assertThat(send(client, "GET", "/v3/api-docs", null, null).statusCode()).isEqualTo(200);
        for (String path : List.of("/unregistered", "/careers/123", "/api/ai/123", "/api/companies-other")) {
            assertProblem(send(client, "GET", path, null, null), 403, "FORBIDDEN");
        }
        assertProblem(send(client, "PUT", "/api/auth/login", "{}", csrf(client)), 403, "FORBIDDEN");
    }

    @Test
    void randomCookieDoesNotAuthenticate() throws Exception {
        assertProblem(withCookie("GET", "/api/auth/me", "arbitrary-test-cookie"), 401, "UNAUTHENTICATED");
    }

    @Test
    void invalidSignupValuesReturnGenericBadRequestWithoutCreatingRows() throws Exception {
        HttpClient client = client();
        String token = csrf(client);
        long companies = companyCount();
        for (Map<String, String> values : List.of(
                Map.of("companyName", " ", "name", "Test", "email", email(), "password", PASSWORD),
                Map.of("companyName", "x".repeat(101), "name", "Test", "email", email(), "password", PASSWORD),
                Map.of("companyName", "Test", "name", " ", "email", email(), "password", PASSWORD),
                Map.of("companyName", "Test", "name", "x".repeat(101), "email", email(), "password", PASSWORD),
                Map.of("companyName", "Test", "name", "Test", "email", "invalid", "password", PASSWORD),
                Map.of("companyName", "Test", "name", "Test", "email", email(), "password", "12345678901"),
                Map.of("companyName", "Test", "name", "Test", "email", email(), "password", " ".repeat(12)),
                Map.of("companyName", "Test", "name", "Test", "email", email(), "password", "x".repeat(129)))) {
            assertProblem(send(client, "POST", "/api/auth/signup", mapper.writeValueAsString(values), token),
                    400, "INVALID_INPUT");
        }
        assertProblem(send(client, "POST", "/api/auth/signup", "{broken", token), 400, "INVALID_INPUT");
        assertThat(companyCount()).isEqualTo(companies);
    }

    @Test
    void passwordsPreserveLeadingAndTrailingSpaces() throws Exception {
        HttpClient client = client();
        String email = email();
        String password = " " + PASSWORD + " ";
        assertThat(send(client, "POST", "/api/auth/signup", signupBody(email, password), csrf(client)).statusCode())
                .isEqualTo(201);
        assertProblem(login(client, email, PASSWORD, csrf(client)), 401, "INVALID_CREDENTIALS");
        assertThat(login(client, email, password, csrf(client)).statusCode()).isEqualTo(200);
    }

    @Test
    void redisSessionContainsOnlySafePrincipalAndNoPassword() throws Exception {
        HttpClient client = client();
        String email = email();
        JsonNode registered = json(signup(client, email));
        login(client, email, PASSWORD, csrf(client));
        String sessionId = sessionId(client);
        Session session = sessions.findById(sessionId);
        assertThat(session).isNotNull();
        assertThat(session.getMaxInactiveInterval()).isEqualTo(Duration.ofMinutes(30));
        SecurityContext context = session.getAttribute("SPRING_SECURITY_CONTEXT");
        assertThat(context.getAuthentication().getCredentials()).isNull();
        assertThat(context.getAuthentication().getPrincipal()).isInstanceOf(MemberPrincipal.class);
        MemberPrincipal member = (MemberPrincipal) context.getAuthentication().getPrincipal();
        assertThat(member.companyId().toString()).isEqualTo(registered.path("companyId").asString());
        assertThat(member.role()).isEqualTo(MemberRole.HR);
        String hash = jdbc.queryForObject("SELECT password_hash FROM members WHERE email = ?", String.class, email);
        try (RedisConnection connection = redis.getConnection()) {
            byte[] bytes = connection.hashCommands().hGet(
                    ("hiremate:sessions:sessions:" + sessionId).getBytes(StandardCharsets.UTF_8),
                    "sessionAttr:SPRING_SECURITY_CONTEXT".getBytes(StandardCharsets.UTF_8));
            assertThat(bytes).isNotNull();
            assertThat(new String(bytes, StandardCharsets.ISO_8859_1))
                    .doesNotContain(PASSWORD, hash, "passwordHash", "MemberUserDetails");
        }
    }

    @Test
    void expiredRedisSessionCannotRestoreAuthentication() throws Exception {
        HttpClient client = client();
        String email = email();
        signup(client, email);
        login(client, email, PASSWORD, csrf(client));
        String cookie = cookie(client);
        String sessionId = sessionId(client);
        assertThat(sessions.findById(sessionId)).isNotNull();
        expireSession(sessions, sessionId);
        assertProblem(withCookie("GET", "/api/auth/me", cookie), 401, "UNAUTHENTICATED");
        assertThat(sessions.findById(sessionId)).isNull();
    }

    @Test
    void storedHashUsesSixHundredThousandPbkdf2IterationsAndSixteenByteSalt() throws Exception {
        String email = email();
        assertThat(signup(client(), email).statusCode()).isEqualTo(201);
        String stored = jdbc.queryForObject("SELECT password_hash FROM members WHERE email = ?", String.class, email);
        String encoded = stored.substring(stored.indexOf('}') + 1);
        byte[] combined = HexFormat.of().parseHex(encoded);
        assertThat(combined).hasSize(48);
        byte[] salt = java.util.Arrays.copyOfRange(combined, 0, 16);
        PBEKeySpec spec = new PBEKeySpec(PASSWORD.toCharArray(), salt, 600_000, 256);
        byte[] expected = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        spec.clearPassword();
        assertThat(java.util.Arrays.copyOfRange(combined, 16, 48)).isEqualTo(expected);
    }

    @Test
    void openApiDescribesAllFiveRealAuthRoutesWithoutInternalPasswordHash() throws Exception {
        HttpClient client = client();
        String email = email();
        signup(client, email);
        login(client, email, PASSWORD, csrf(client));
        HttpResponse<String> response = send(client, "GET", "/v3/api-docs", null, null);
        assertThat(response.statusCode()).isEqualTo(200);
        JsonNode paths = json(response).path("paths");
        assertThat(paths.path("/api/auth/csrf").path("get").isMissingNode()).isFalse();
        assertThat(paths.path("/api/auth/signup").path("post").isMissingNode()).isFalse();
        assertThat(paths.path("/api/auth/login").path("post").isMissingNode()).isFalse();
        assertThat(paths.path("/api/auth/logout").path("post").isMissingNode()).isFalse();
        assertThat(paths.path("/api/auth/me").path("get").isMissingNode()).isFalse();
        assertThat(response.body()).doesNotContain("passwordHash", "password_hash", "MemberUserDetails");
    }

    private String sessionId(HttpClient client) {
        return new String(Base64.getDecoder().decode(cookie(client)), StandardCharsets.UTF_8);
    }

    private <S extends Session> void expireSession(SessionRepository<S> repository, String id) {
        S session = repository.findById(id);
        session.setLastAccessedTime(Instant.now().minus(Duration.ofMinutes(31)));
        repository.save(session);
    }

    private long companyCount() {
        return jdbc.queryForObject("SELECT count(*) FROM companies", Long.class);
    }

    private String email() {
        return "test-" + UUID.randomUUID() + "@example.com";
    }

    private HttpClient client() {
        return HttpClient.newBuilder().cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL)).build();
    }

    private String cookie(HttpClient client) {
        CookieManager cookies = (CookieManager) client.cookieHandler().orElseThrow();
        return cookies.getCookieStore().getCookies().stream().filter(value -> value.getName().equals("SESSION"))
                .findFirst().map(HttpCookie::getValue).orElseThrow();
    }

    private String csrf(HttpClient client) throws Exception {
        HttpResponse<String> response = send(client, "GET", "/api/auth/csrf", null, null);
        assertThat(response.statusCode()).isEqualTo(200);
        return json(response).path("token").asString();
    }

    private String signupBody(String email, String password) {
        return mapper.writeValueAsString(Map.of("companyName", "Test company", "name", "Test HR", "email", email,
                "password", password));
    }

    private HttpResponse<String> signup(HttpClient client, String email) throws Exception {
        return send(client, "POST", "/api/auth/signup", signupBody(email, PASSWORD), csrf(client));
    }

    private HttpResponse<String> login(HttpClient client, String email, String password, String token)
            throws Exception {
        return send(client, "POST", "/api/auth/login", mapper.writeValueAsString(Map.of("email", email,
                "password", password)), token);
    }

    private JsonNode json(HttpResponse<String> response) {
        return mapper.readTree(response.body());
    }

    private void assertProblem(HttpResponse<String> response, int status, String code) {
        assertThat(response.statusCode()).isEqualTo(status);
        assertThat(response.headers().firstValue("Content-Type").orElseThrow())
                .startsWith("application/problem+json");
        assertThat(json(response).path("code").asString()).isEqualTo(code);
        assertThat(response.body()).doesNotContain(PASSWORD, "password_hash", "SQLException");
    }

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpRequest request(String method, String path, String body, String token) {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path)).header("Content-Type", "application/json");
        if (token != null) {
            request.header("X-CSRF-TOKEN", token);
        }
        return request.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body)).build();
    }

    private HttpResponse<String> send(HttpClient client, String method, String path, String body, String token)
            throws Exception {
        return client.send(request(method, path, body, token), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> withCookie(String method, String path, String cookie) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri(path)).header("Cookie", "SESSION=" + cookie)
                .method(method, HttpRequest.BodyPublishers.noBody()).build();
        return HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
    }
}
