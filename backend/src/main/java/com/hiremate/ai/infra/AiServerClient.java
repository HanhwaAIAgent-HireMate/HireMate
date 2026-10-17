package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.global.ApiException;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * ai 서버(ai/) HTTP 클라이언트. Remote Agent 구현은 이 클라이언트로만 ai 서버를 부른다.
 *
 * <p>경로는 /agents/{agent}/{method}이고, 요청 본문은 Agent 메서드의 매개변수 이름을 키로 한 JSON 객체,
 * 응답 본문은 메서드 반환 타입의 JSON이다. 연결 실패 · 시간 초과 · 오류 응답은 502 AI_UNAVAILABLE로 바꾼다.
 */
@Component
class AiServerClient {

    private static final Logger log = LoggerFactory.getLogger(AiServerClient.class);

    private final WebClient client;
    private final Duration timeout;

    AiServerClient(WebClient.Builder builder, @Value("${hiremate.ai.base-url}") String baseUrl,
            @Value("${hiremate.ai.timeout:60s}") Duration timeout) {
        this.client = builder.baseUrl(baseUrl).build();
        this.timeout = timeout;
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

    private static ApiException unavailable() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "The AI server is not available.");
    }
}
