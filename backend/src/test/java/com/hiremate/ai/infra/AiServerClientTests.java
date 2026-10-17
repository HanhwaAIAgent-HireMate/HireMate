package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.global.ApiException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class AiServerClientTests {

    private final AtomicReference<ClientRequest> sent = new AtomicReference<>();

    @Test
    @DisplayName("/agents/{agent}/{method}로 보내고 응답 JSON을 타입으로 읽는다")
    void postsToAgentPath() {
        AiServerClient client = client(request -> {
            sent.set(request);
            return Mono.just(json(HttpStatus.OK, "{\"reply\":\"ok\"}"));
        }, Duration.ofSeconds(1));

        Reply reply = client.post(AiAgent.CANDIDATE_ANALYST, "analyze", Map.of("message", "hi"), Reply.class);

        assertThat(reply).isEqualTo(new Reply("ok"));
        assertThat(sent.get().method()).isEqualTo(HttpMethod.POST);
        assertThat(sent.get().url()).hasToString("http://ai.test/agents/candidate-analyst/analyze");
    }

    @Test
    @DisplayName("목록 같은 제네릭 응답도 읽는다")
    void readsGenericResponse() {
        AiServerClient client = client(request -> Mono.just(json(HttpStatus.OK, "[\"a\",\"b\"]")),
                Duration.ofSeconds(1));

        List<String> questions = client.post(AiAgent.INTERVIEW, "questions", Map.of(),
                new ParameterizedTypeReference<List<String>>() { });

        assertThat(questions).containsExactly("a", "b");
    }

    @Test
    @DisplayName("ai 서버가 오류를 돌려주면 502 AI_UNAVAILABLE이다")
    void mapsErrorResponse() {
        AiServerClient client = client(request -> Mono.just(json(HttpStatus.INTERNAL_SERVER_ERROR, "{}")),
                Duration.ofSeconds(1));

        assertUnavailable(() -> client.post(AiAgent.ROOT, "plan", Map.of(), Reply.class));
    }

    @Test
    @DisplayName("응답이 늦으면 502 AI_UNAVAILABLE이다")
    void mapsTimeout() {
        AiServerClient client = client(request -> Mono.never(), Duration.ofMillis(50));

        assertUnavailable(() -> client.post(AiAgent.ROOT, "plan", Map.of(), Reply.class));
    }

    @Test
    @DisplayName("연결하지 못하면 502 AI_UNAVAILABLE이다")
    void mapsConnectionFailure() {
        AiServerClient client = client(request -> Mono.error(new IllegalStateException("connection refused")),
                Duration.ofSeconds(1));

        assertUnavailable(() -> client.post(AiAgent.ROOT, "plan", Map.of(), Reply.class));
    }

    private static AiServerClient client(ExchangeFunction exchange, Duration timeout) {
        return new AiServerClient(WebClient.builder().exchangeFunction(exchange), "http://ai.test", timeout);
    }

    private static ClientResponse json(HttpStatus status, String body) {
        return ClientResponse.create(status)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body(body)
                .build();
    }

    private static void assertUnavailable(Runnable call) {
        assertThatThrownBy(call::run)
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.status()).isEqualTo(HttpStatus.BAD_GATEWAY);
                    assertThat(exception.code()).isEqualTo("AI_UNAVAILABLE");
                });
    }

    record Reply(String reply) {
    }
}
