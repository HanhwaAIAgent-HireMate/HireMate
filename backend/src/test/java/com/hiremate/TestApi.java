package com.hiremate;

import java.io.ByteArrayOutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 세션 쿠키와 CSRF 토큰을 유지하는 테스트용 HTTP 클라이언트. */
public final class TestApi {

    static final JsonMapper MAPPER = new JsonMapper();

    private final int port;
    private final HttpClient client;
    private String csrf;
    private JsonNode member;

    TestApi(int port) {
        this.port = port;
        CookieManager cookies = new CookieManager();
        cookies.setCookiePolicy(CookiePolicy.ACCEPT_ALL);
        this.client = HttpClient.newBuilder().cookieHandler(cookies).build();
    }

    void signupAndLogin() throws Exception {
        String email = "hr-" + UUID.randomUUID() + "@example.com";
        String password = "test-password-2026";
        expect(post("/api/auth/signup", Map.of("companyName", "테스트 기업", "name", "최은영", "email", email,
                "password", password)), 201);
        member = json(expect(post("/api/auth/login", Map.of("email", email, "password", password)), 200));
        csrf = null;
    }

    /** 이미 있는 계정으로 로그인한다. 면접관 계정처럼 HR이 만든 계정에 쓴다. */
    public void login(String email, String password) throws Exception {
        member = json(expect(post("/api/auth/login", Map.of("email", email, "password", password)), 200));
        csrf = null;
    }

    public UUID memberId() {
        return UUID.fromString(member.path("memberId").asString());
    }

    public UUID companyId() {
        return UUID.fromString(member.path("companyId").asString());
    }

    public HttpResponse<String> get(String path) throws Exception {
        return send(HttpRequest.newBuilder(uri(path)).GET());
    }

    public HttpResponse<byte[]> getBytes(String path) throws Exception {
        return client.send(HttpRequest.newBuilder(uri(path)).GET().build(), HttpResponse.BodyHandlers.ofByteArray());
    }

    public HttpResponse<String> post(String path, Object body) throws Exception {
        return send(withJson(HttpRequest.newBuilder(uri(path)), "POST", body));
    }

    public HttpResponse<String> put(String path, Object body) throws Exception {
        return send(withJson(HttpRequest.newBuilder(uri(path)), "PUT", body));
    }

    public HttpResponse<String> patch(String path, Object body) throws Exception {
        return send(withJson(HttpRequest.newBuilder(uri(path)), "PATCH", body));
    }

    public HttpResponse<String> delete(String path) throws Exception {
        return send(HttpRequest.newBuilder(uri(path)).header(csrfHeader(), csrf()).DELETE());
    }

    /** parts의 값이 {@link FilePart}면 파일, 아니면 문자열 필드로 보낸다. */
    public HttpResponse<String> multipart(String path, Map<String, Object> parts) throws Exception {
        String boundary = "----hiremate" + UUID.randomUUID();
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        for (Map.Entry<String, Object> part : parts.entrySet()) {
            body.writeBytes(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            if (part.getValue() instanceof FilePart file) {
                body.writeBytes(("Content-Disposition: form-data; name=\"" + part.getKey() + "\"; filename=\""
                        + file.name() + "\"\r\nContent-Type: " + file.contentType() + "\r\n\r\n")
                        .getBytes(StandardCharsets.UTF_8));
                body.writeBytes(file.content());
            } else {
                body.writeBytes(("Content-Disposition: form-data; name=\"" + part.getKey() + "\"\r\n\r\n"
                        + part.getValue()).getBytes(StandardCharsets.UTF_8));
            }
            body.writeBytes("\r\n".getBytes(StandardCharsets.UTF_8));
        }
        body.writeBytes(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        return send(HttpRequest.newBuilder(uri(path))
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .header(csrfHeader(), csrf())
                .POST(HttpRequest.BodyPublishers.ofByteArray(body.toByteArray())));
    }

    public static JsonNode json(HttpResponse<String> response) {
        return MAPPER.readTree(response.body());
    }

    /** SSE 응답 본문의 이벤트. (이벤트 이름, data JSON)을 받은 순서대로 돌려준다. */
    public static List<Map.Entry<String, JsonNode>> events(HttpResponse<String> response) {
        List<Map.Entry<String, JsonNode>> events = new ArrayList<>();
        for (String block : response.body().replace("\r\n", "\n").split("\n\n")) {
            String name = null;
            StringBuilder data = new StringBuilder();
            for (String line : block.split("\n")) {
                if (line.startsWith("event:")) {
                    name = line.substring("event:".length()).trim();
                } else if (line.startsWith("data:")) {
                    data.append(line.substring("data:".length()));
                }
            }
            if (name != null) {
                events.add(Map.entry(name, MAPPER.readTree(data.toString())));
            }
        }
        return events;
    }

    /**
     * SSE 응답의 done 이벤트 data. done 뒤에는 탭 제목(title)만 올 수 있다. done이 없거나 그 뒤에 다른 이벤트가 오면
     * 실패다.
     */
    public static JsonNode done(HttpResponse<String> response) {
        List<Map.Entry<String, JsonNode>> events = new ArrayList<>(events(response));
        if (!events.isEmpty() && events.getLast().getKey().equals("title")) {
            events.removeLast();
        }
        if (events.isEmpty() || !events.getLast().getKey().equals("done")) {
            throw new AssertionError("Expected a done event: " + response.body());
        }
        return events.getLast().getValue();
    }

    public static HttpResponse<String> expect(HttpResponse<String> response, int status) {
        if (response.statusCode() != status) {
            throw new AssertionError("Expected " + status + " but was " + response.statusCode() + ": "
                    + response.body());
        }
        return response;
    }

    private HttpRequest.Builder withJson(HttpRequest.Builder builder, String method, Object body) throws Exception {
        String json = body == null ? "{}" : MAPPER.writeValueAsString(body);
        return builder.header("Content-Type", "application/json").header(csrfHeader(), csrf())
                .method(method, HttpRequest.BodyPublishers.ofString(json));
    }

    private String csrf() throws Exception {
        if (csrf == null) {
            HttpResponse<String> response = send(HttpRequest.newBuilder(uri("/api/auth/csrf")).GET());
            csrf = json(response).path("token").asString();
        }
        return csrf;
    }

    private static String csrfHeader() {
        return "X-CSRF-TOKEN";
    }

    private HttpResponse<String> send(HttpRequest.Builder builder) throws Exception {
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    public record FilePart(String name, String contentType, byte[] content) {
    }
}
