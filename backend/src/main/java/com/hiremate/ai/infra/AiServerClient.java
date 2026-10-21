package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.global.ApiException;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
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
 *
 * <p>지원 접수 분석(Application Agent)은 화면이 기다리지 않는 이벤트에서 부르고 모델을 여러 번 불러, 따로 더 기다린다.
 */
@Component
class AiServerClient {

    private static final Logger log = LoggerFactory.getLogger(AiServerClient.class);

    private final WebClient client;
    private final Duration timeout;
    private final Duration applicationTimeout;

    AiServerClient(WebClient.Builder builder, String baseUrl, Duration timeout) {
        this(builder, baseUrl, timeout, timeout);
    }

    @Autowired
    AiServerClient(WebClient.Builder builder, @Value("${hiremate.ai.base-url}") String baseUrl,
            @Value("${hiremate.ai.timeout:60s}") Duration timeout,
            @Value("${hiremate.ai.application-timeout:180s}") Duration applicationTimeout) {
        this.client = builder.baseUrl(baseUrl).build();
        this.timeout = timeout;
        this.applicationTimeout = applicationTimeout;
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
                    .timeout(agent == AiAgent.APPLICATION ? applicationTimeout : timeout)
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
