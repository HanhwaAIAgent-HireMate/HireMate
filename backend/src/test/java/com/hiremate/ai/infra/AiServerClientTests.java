package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.global.ApiException;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import tools.jackson.databind.json.JsonMapper;

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

    private static final String STATUS = "event:status\ndata:{\"text\":\"요청을 확인하고 있어요\"}\n\n";
    private static final String ITEM = "event:item\ndata:{\"applicationId\":null,\"label\":\"RDBMS\","
            + "\"text\":\"Oracle 원장 설계\",\"status\":\"OK\"}\n\n";
    private static final String DONE = "event:done\ndata:{\"reply\":\"ok\"}\n\n";

    @Test
    @DisplayName("SSE를 받아 status · item은 진행 알림으로 넘기고 done을 타입으로 읽는다")
    void streamsStatusItemAndDone() {
        AiServerClient client = client(request -> {
            sent.set(request);
            return Mono.just(sse(Flux.just(STATUS, ITEM, DONE)));
        }, Duration.ofSeconds(1));
        Recorded progress = new Recorded();

        Reply reply = client.stream(AiAgent.ROOT, "plan", Map.of("message", "hi"), Reply.class, progress);

        assertThat(reply).isEqualTo(new Reply("ok"));
        assertThat(progress.events).containsExactly("status:요청을 확인하고 있어요", "item:RDBMS");
        assertThat(sent.get().url()).hasToString("http://ai.test/agents/root/plan");
        assertThat(sent.get().headers().getAccept()).containsExactly(MediaType.TEXT_EVENT_STREAM);
    }

    @Test
    @DisplayName("keepalive 주석과 모르는 이벤트는 건너뛴다")
    void ignoresCommentsAndUnknownEvents() {
        AiServerClient client = client(request -> Mono.just(sse(Flux.just(": ping\n\n", "event:other\ndata:{}\n\n",
                DONE))), Duration.ofSeconds(1));
        Recorded progress = new Recorded();

        Reply reply = client.stream(AiAgent.ROOT, "plan", Map.of(), Reply.class, progress);

        assertThat(reply).isEqualTo(new Reply("ok"));
        assertThat(progress.events).isEmpty();
    }

    @Test
    @DisplayName("done 없이 스트림이 끝나면 502 AI_UNAVAILABLE이다")
    void streamWithoutDoneIsUnavailable() {
        AiServerClient client = client(request -> Mono.just(sse(Flux.just(STATUS))), Duration.ofSeconds(1));

        assertUnavailable(() -> client.stream(AiAgent.ROOT, "plan", Map.of(), Reply.class, new Recorded()));
    }

    @Test
    @DisplayName("스트림 요청에 오류 응답이면 502 AI_UNAVAILABLE이다")
    void streamErrorStatusIsUnavailable() {
        AiServerClient client = client(request -> Mono.just(json(HttpStatus.INTERNAL_SERVER_ERROR, "{}")),
                Duration.ofSeconds(1));

        assertUnavailable(() -> client.stream(AiAgent.ROOT, "plan", Map.of(), Reply.class, new Recorded()));
    }

    @Test
    @DisplayName("시간 제한은 이벤트 간격이 아니라 스트림 전체에 건다")
    void streamTimeoutIsWhole() {
        Flux<String> endless = Flux.interval(Duration.ofMillis(20)).map(tick -> STATUS);
        AiServerClient client = client(request -> Mono.just(sse(endless)), Duration.ofMillis(150));

        assertUnavailable(() -> client.stream(AiAgent.ROOT, "plan", Map.of(), Reply.class, new Recorded()));
    }

    @Test
    @DisplayName("진행 알림을 보내지 못하면(화면 연결 끊김) ai 서버 요청을 끊고 그 예외를 그대로 올린다")
    void progressFailureCancelsAndPropagates() {
        AtomicBoolean cancelled = new AtomicBoolean();
        Flux<String> body = Flux.concat(Flux.just(STATUS), Flux.<String>never()).doOnCancel(() -> cancelled.set(true));
        AiServerClient client = client(request -> Mono.just(sse(body)), Duration.ofSeconds(1));
        ChatProgress gone = new Recorded() {
            @Override
            public void status(String text) {
                throw new UncheckedIOException(new IOException("Broken pipe"));
            }
        };

        assertThatThrownBy(() -> client.stream(AiAgent.ROOT, "plan", Map.of(), Reply.class, gone))
                .isInstanceOf(UncheckedIOException.class);
        assertThat(cancelled).isTrue();
    }

    private static AiServerClient client(ExchangeFunction exchange, Duration timeout) {
        return new AiServerClient(WebClient.builder().exchangeFunction(exchange), "http://ai.test", timeout,
                JsonMapper.builder().build());
    }

    private static ClientResponse sse(Flux<String> events) {
        Flux<DataBuffer> body = events.map(event -> DefaultDataBufferFactory.sharedInstance
                .wrap(event.getBytes(StandardCharsets.UTF_8)));
        return ClientResponse.create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_EVENT_STREAM_VALUE)
                .body(body)
                .build();
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

    static class Recorded implements ChatProgress {

        final List<String> events = new ArrayList<>();

        @Override
        public void status(String text) {
            events.add("status:" + text);
        }

        @Override
        public void item(ChatItem item) {
            events.add("item:" + item.label());
        }
    }
}
