package com.hiremate.company.application;

import com.hiremate.global.ApiException;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.UriComponentsBuilder;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Canva의 공개 OAuth 메타데이터에서 확인한 MCP 전용 경로만 사용한다. 비밀값은 로그에 남기지 않는다. */
@Component
public class CanvaClient {

    private static final String MCP = "https://api.canva.com/connect/v1/mcp";
    private static final String TOKEN = "https://api.canva.com/auth/v1/oauth/token";
    private static final String SCOPES = "profile:read design:meta:read design:content:read design:content:write"
            + " asset:read asset:write";
    private final WebClient http;
    private final JsonMapper json;
    private final String clientId;
    private final String clientSecret;

    public CanvaClient(WebClient.Builder builder, JsonMapper json,
            @Value("${CANVA_CLIENT_ID:}") String clientId,
            @Value("${CANVA_CLIENT_SECRET:}") String clientSecret) {
        this.http = builder.codecs(config -> config.defaultCodecs().maxInMemorySize(1024 * 1024)).build();
        this.json = json;
        this.clientId = clientId.strip();
        this.clientSecret = clientSecret.strip();
    }

    public boolean configured() {
        return !clientId.isEmpty() && !clientSecret.isEmpty();
    }

    public String authorizeUrl(String redirect, String state, String challenge) {
        if (!configured()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "CANVA_NOT_CONFIGURED",
                    "Canva 서버 연결 설정이 필요해요.");
        }
        return UriComponentsBuilder.fromUriString("https://www.canva.com/api/oauth/authorize")
                .queryParam("client_id", clientId).queryParam("response_type", "code")
                .queryParam("redirect_uri", redirect).queryParam("state", state)
                .queryParam("code_challenge", challenge).queryParam("code_challenge_method", "S256")
                .queryParam("scope", SCOPES).queryParam("resource", MCP).build().encode().toUriString();
    }

    public Tokens exchange(String code, String verifier, String redirect) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "authorization_code");
        form.add("code", code);
        form.add("code_verifier", verifier);
        form.add("redirect_uri", redirect);
        form.add("resource", MCP);
        return token(form, null);
    }

    public Tokens refresh(String refreshToken) {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type", "refresh_token");
        form.add("refresh_token", refreshToken);
        form.add("resource", MCP);
        return token(form, refreshToken);
    }

    private Tokens token(MultiValueMap<String, String> form, String oldRefresh) {
        try {
            JsonNode reply = http.post().uri(TOKEN).headers(headers -> headers.setBasicAuth(clientId, clientSecret))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED).body(BodyInserters.fromFormData(form))
                    .retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(20));
            if (reply == null || reply.path("access_token").asString("").isBlank()
                    || !reply.path("token_type").asString("").equalsIgnoreCase("Bearer")) {
                throw unavailable();
            }
            long seconds = reply.path("expires_in").asLong(0);
            if (seconds <= 0) {
                throw unavailable();
            }
            return new Tokens(reply.path("access_token").asString(),
                    reply.path("refresh_token").asString(oldRefresh), Instant.now().plusSeconds(seconds));
        } catch (RuntimeException exception) {
            // HTTP 오류 본문과 예외에는 code, token 등이 들어갈 수 있어 밖으로 전파하거나 로그에 쓰지 않는다.
            throw unavailable();
        }
    }

    public List<String> availableTools(String accessToken) {
        Map<String, Object> initialized = rpc("initialize", 1, Map.of("protocolVersion", "2025-03-26",
                "capabilities", Map.of(), "clientInfo", Map.of("name", "HireMate", "version", "1")));
        RpcResult init = send(accessToken, initialized, null, null);
        String protocol = init.body().path("result").path("protocolVersion").asString("");
        if (protocol.isBlank()) {
            throw unavailable();
        }
        send(accessToken, Map.of("jsonrpc", "2.0", "method", "notifications/initialized"), init.session(), protocol);
        JsonNode result = send(accessToken, rpc("tools/list", 2, Map.of()), init.session(), protocol).body();
        JsonNode tools = result.path("result").path("tools");
        if (!tools.isArray()) {
            throw unavailable();
        }
        List<String> names = new ArrayList<>();
        for (JsonNode item : tools) {
            String name = item.path("name").asString("");
            if (!name.isBlank()) {
                names.add(name);
            }
        }
        return List.copyOf(names);
    }

    /** 정해진 디자인 도구만 호출한다. 토큰이나 임의 MCP 서버 주소는 Agent에 전달하지 않는다. */
    public JsonNode designTool(String accessToken, String name, Map<String, Object> arguments) {
        Set<String> allowed = Set.of("search-designs", "get-design", "get-design-pages",
                "start-editing-transaction", "perform-editing-operations", "cancel-editing-transaction",
                "get-design-thumbnail", "copy-design", "get-export-formats", "export-design");
        if (!allowed.contains(name)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "CANVA_TOOL_NOT_ALLOWED", "지원하지 않는 Canva 작업이에요.");
        }
        RpcResult init = send(accessToken, rpc("initialize", 1, Map.of("protocolVersion", "2025-03-26",
                "capabilities", Map.of(), "clientInfo", Map.of("name", "HireMate", "version", "1"))), null, null);
        String protocol = init.body().path("result").path("protocolVersion").asString("");
        if (protocol.isBlank()) {
            throw unavailable();
        }
        send(accessToken, Map.of("jsonrpc", "2.0", "method", "notifications/initialized"), init.session(), protocol);
        JsonNode result = send(accessToken, rpc("tools/call", 2, Map.of("name", name, "arguments", arguments)),
                init.session(), protocol).body().path("result");
        if (result.path("isError").asBoolean(false)) {
            throw unavailable();
        }
        JsonNode structured = result.path("structuredContent");
        if (!structured.isMissingNode() && !structured.isNull()) {
            return structured;
        }
        for (JsonNode block : result.path("content")) {
            if ("text".equals(block.path("type").asString())) {
                try {
                    return json.readTree(block.path("text").asString());
                } catch (RuntimeException exception) {
                    throw unavailable();
                }
            }
        }
        throw unavailable();
    }

    public byte[] previewImage(String url) {
        URI uri;
        try {
            uri = URI.create(url);
        } catch (IllegalArgumentException exception) {
            throw unavailable();
        }
        String host = uri.getHost();
        if (!"https".equals(uri.getScheme()) || host == null || uri.getUserInfo() != null
                || uri.getPort() != -1 || !Set.of("export-download.canva.com",
                        "design-manipulation-download.canva.com", "media.canva.com").contains(host)) {
            throw unavailable();
        }
        try {
            // 기본 WebClient는 리디렉션을 따르지 않으며 응답 본문은 1MB로 제한된다.
            byte[] bytes = http.get().uri(uri).retrieve().bodyToMono(byte[].class).block(Duration.ofSeconds(20));
            if (bytes == null || bytes.length == 0) {
                throw unavailable();
            }
            return bytes;
        } catch (RuntimeException exception) {
            throw unavailable();
        }
    }

    private RpcResult send(String accessToken, Map<String, Object> body, String session, String protocol) {
        try {
            return http.post().uri(MCP).headers(headers -> {
                headers.setBearerAuth(accessToken);
                headers.set(HttpHeaders.ACCEPT, "application/json, text/event-stream");
                if (session != null) {
                    headers.set("Mcp-Session-Id", session);
                }
                if (protocol != null) {
                    headers.set("MCP-Protocol-Version", protocol);
                }
            }).contentType(MediaType.APPLICATION_JSON).bodyValue(body).exchangeToMono(response -> {
                if (!response.statusCode().is2xxSuccessful()) {
                    return response.createError();
                }
                String sessionId = response.headers().asHttpHeaders().getFirst("Mcp-Session-Id");
                return response.bodyToMono(String.class).defaultIfEmpty("")
                        .map(text -> new RpcResult(readRpc(text, body.get("id")), sessionId));
            }).block(Duration.ofSeconds(20));
        } catch (RuntimeException exception) {
            throw unavailable();
        }
    }

    private JsonNode readRpc(String text, Object id) {
        if (id == null && text.isBlank()) {
            return json.createObjectNode();
        }
        List<String> candidates = text.stripLeading().startsWith("{") ? List.of(text)
                : text.lines().filter(line -> line.startsWith("data:"))
                        .map(line -> line.substring(5).strip()).toList();
        for (String candidate : candidates) {
            JsonNode result = json.readTree(candidate);
            if (result.path("id").asString("").equals(String.valueOf(id))) {
                if (result.has("error")) {
                    throw unavailable();
                }
                return result;
            }
        }
        throw unavailable();
    }

    private static Map<String, Object> rpc(String method, int id, Map<String, Object> params) {
        return Map.of("jsonrpc", "2.0", "id", id, "method", method, "params", params);
    }

    private static ApiException unavailable() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "CANVA_UNAVAILABLE",
                "Canva 연결을 확인하지 못했어요. 앱 설정과 승인 범위를 확인해 주세요.");
    }

    private record RpcResult(JsonNode body, String session) {
    }

    /** 서버 로그인 세션에만 보관하고 API 응답에 사용하지 않는다. */
    public record Tokens(String accessToken, String refreshToken, Instant expiresAt) {
        @Override
        public String toString() {
            return "Canva tokens [redacted]";
        }
    }
}
