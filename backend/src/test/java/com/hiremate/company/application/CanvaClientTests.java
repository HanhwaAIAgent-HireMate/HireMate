package com.hiremate.company.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.global.ApiException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import tools.jackson.databind.json.JsonMapper;

class CanvaClientTests {

    @Test
    void authorizeUsesPkceAndMinimalScopesWithoutTheClientSecret() {
        CanvaClient client = new CanvaClient(WebClient.builder(), new JsonMapper(), "client-id", "secret-value");
        String url = client.authorizeUrl("http://localhost:5173/api/companies/me/canva/callback", "state", "challenge");
        assertThat(url).startsWith("https://www.canva.com/api/oauth/authorize?")
                .contains("code_challenge_method=S256", "code_challenge=challenge", "state=state")
                .doesNotContain("secret-value", "brandkit", "comment", "folder");
        assertThat(new CanvaClient(WebClient.builder(), new JsonMapper(), "", "").configured()).isFalse();
    }

    @Test
    void mcpInitializationAndToolDiscoverySupportSseWithoutExposingTokens() {
        List<ClientRequest> sent = new ArrayList<>();
        AtomicInteger calls = new AtomicInteger();
        WebClient.Builder builder = WebClient.builder().exchangeFunction(request -> {
            sent.add(request);
            int index = calls.incrementAndGet();
            if (index == 2) {
                return Mono.just(ClientResponse.create(HttpStatus.ACCEPTED).build());
            }
            String body = index == 1
                    ? "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"protocolVersion\":\"2025-03-26\"}}\n\n"
                    : "data: {\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"tools\":[{\"name\":\"search-designs\"}]}}\n\n";
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Mcp-Session-Id", "canva-session")
                    .header("Content-Type", "text/event-stream").body(body).build());
        });
        CanvaClient client = new CanvaClient(builder, new JsonMapper(), "client", "secret");
        assertThat(client.availableTools("private-token")).containsExactly("search-designs");
        assertThat(sent).hasSize(3);
        assertThat(sent.get(2).headers().getFirst("Mcp-Session-Id")).isEqualTo("canva-session");
        assertThat(sent.get(2).headers().getFirst("MCP-Protocol-Version")).isEqualTo("2025-03-26");
        assertThat(sent.get(2).headers().getFirst("Authorization")).isEqualTo("Bearer private-token");
    }

    @Test
    void invalidOauthResponseAndUpstreamErrorsAreSanitized() {
        WebClient.Builder builder = WebClient.builder().exchangeFunction(request -> Mono.just(
                ClientResponse.create(HttpStatus.BAD_REQUEST).header("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                        .body("{\"error_description\":\"private-token-and-secret\"}").build()));
        CanvaClient client = new CanvaClient(builder, new JsonMapper(), "client", "secret");
        assertThatThrownBy(() -> client.exchange("code", "verifier", "http://localhost:5173/callback"))
                .isInstanceOf(ApiException.class).hasMessageNotContaining("private-token-and-secret");
        assertThatThrownBy(() -> client.availableTools("private-token"))
                .isInstanceOf(ApiException.class).hasMessageNotContaining("private-token-and-secret");
    }

    @Test
    void previewRejectsExternalHostsAndToolCallsRejectUnlistedOperations() {
        CanvaClient client = new CanvaClient(WebClient.builder(), new JsonMapper(), "client", "secret");
        for (String url : List.of("http://127.0.0.1/private", "https://media.canva.com.evil.test/image",
                "https://media.canva.com:123/image", "https://user@media.canva.com/image")) {
            assertThatThrownBy(() -> client.previewImage(url)).isInstanceOf(ApiException.class);
        }
        assertThatThrownBy(() -> client.designTool("private-token", "delete-design", java.util.Map.of()))
                .isInstanceOf(ApiException.class);
    }
}
