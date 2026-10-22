package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.ChatStatus;
import com.hiremate.global.ApiException;
import java.io.UncheckedIOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.json.JsonMapper;

/**
 * ai 서버(ai/) HTTP 클라이언트. Remote Agent 구현은 이 클라이언트로만 ai 서버를 부른다.
 *
 * <p>경로는 /agents/{agent}/{method}이고, 요청 본문은 Agent 메서드의 매개변수 이름을 키로 한 JSON 객체,
 * 응답 본문은 메서드 반환 타입의 JSON이다. 연결 실패 · 시간 초과 · 오류 응답은 502 AI_UNAVAILABLE로 바꾼다.
 *
 * <p>Root plan은 SSE로 받는다({@link #stream}). status · item 이벤트는 진행 알림으로 넘기고 done 이벤트가 결과다.
 *
 * <p>지원 접수 분석(Application Agent)은 이 클라이언트로 기다리지 않고 job 모듈의 대기열로 AI 워커에 맡긴다.
 */
@Component
class AiServerClient {

    private static final Logger log = LoggerFactory.getLogger(AiServerClient.class);
    private static final ParameterizedTypeReference<ServerSentEvent<String>> EVENTS =
            new ParameterizedTypeReference<>() { };

    private final WebClient client;
    private final Duration timeout;
    private final JsonMapper json;

    AiServerClient(WebClient.Builder builder, @Value("${hiremate.ai.base-url}") String baseUrl,
            @Value("${hiremate.ai.timeout:60s}") Duration timeout, JsonMapper json) {
        this.client = builder.baseUrl(baseUrl).build();
        this.timeout = timeout;
        this.json = json;
    }

    <T> T post(AiAgent agent, String method, Object body, Class<T> type) {
        return post(agent, method, body, ParameterizedTypeReference.forType(type));
    }

    <T> T post(AiAgent agent, String method, Object body, ParameterizedTypeReference<T> type) {
        String path = "/agents/" + agent.key() + "/" + method;
        T response;
        try {
            response = client.post()
                    .uri(path)
                    .bodyValue(body)
                    .retrieve()
                    .bodyToMono(type)
                    .timeout(timeout)
                    .block();
        } catch (RuntimeException exception) {
            log.warn("AI server call failed: {}", path, exception);
            throw unavailable();
        }
        if (response == null) {
            log.warn("AI server returned an empty body: {}", path);
            throw unavailable();
        }
        return response;
    }

    /**
     * SSE로 받는다. 시간 제한은 이벤트 사이 간격이 아니라 스트림 전체에 건다. done 없이 끝나면 502다.
     * progress가 {@link UncheckedIOException}을 던지면(화면 연결 끊김) 구독을 끊어 ai 서버 요청도 멈추고 그 예외를 올린다.
     */
    <T> T stream(AiAgent agent, String method, Object body, Class<T> type, ChatProgress progress) {
        String path = "/agents/" + agent.key() + "/" + method;
        AtomicReference<T> done = new AtomicReference<>();
        try {
            client.post()
                    .uri(path)
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .bodyValue(body)
                    .retrieve()
                    .bodyToFlux(EVENTS)
                    .doOnNext(event -> receive(event, type, progress, done))
                    .blockLast(timeout);
        } catch (UncheckedIOException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            log.warn("AI server stream failed: {}", path, exception);
            throw unavailable();
        }
        if (done.get() == null) {
            log.warn("AI server stream ended without done: {}", path);
            throw unavailable();
        }
        return done.get();
    }

    private <T> void receive(ServerSentEvent<String> event, Class<T> type, ChatProgress progress,
            AtomicReference<T> done) {
        // 이름이 없으면 keepalive 주석이다
        if (event.event() == null || event.data() == null) {
            return;
        }
        switch (event.event()) {
            case "status" -> progress.status(json.readValue(event.data(), ChatStatus.class).text());
            case "item" -> progress.item(json.readValue(event.data(), ChatItem.class));
            case "done" -> done.set(json.readValue(event.data(), type));
            default -> {}
        }
    }

    private static ApiException unavailable() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "The AI server is not available.");
    }
}
