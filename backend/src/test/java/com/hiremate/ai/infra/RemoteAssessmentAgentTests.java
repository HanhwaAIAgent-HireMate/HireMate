package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteAssessmentAgentTests {

    private final AtomicReference<String> path = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private HttpServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            path.set(exchange.getRequestURI().getPath());
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = "{\"status\": \"DONE\", \"saved\": 2, \"dropped\": 1}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    @Test
    @DisplayName("ai 서버의 /agents/assessment/analyze에 input을 보내고, 점수가 없는 영역은 null로 보낸다")
    void postsInputAndReadsResult() {
        String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
        RemoteAssessmentAgent agent = new RemoteAssessmentAgent(
                new AiServerClient(WebClient.builder(), baseUrl, Duration.ofSeconds(5)));
        Map<String, BigDecimal> areas = new LinkedHashMap<>();
        areas.put("의사소통능력", new BigDecimal("80"));
        areas.put("수리능력", null);
        UUID stageId = UUID.randomUUID();
        AssessmentInput input = new AssessmentInput(UUID.randomUUID(), UUID.randomUUID(), stageId, UUID.randomUUID(),
                "직무역량 평가", new BigDecimal("82.5"), areas, "B", null, "https://github.com/example/assignment",
                "코드 구조 설명이 명확했음");

        AssessmentAgent.AnalyzeResult result = agent.analyze(input);

        assertThat(path.get()).isEqualTo("/agents/assessment/analyze");
        JsonNode sent = JsonMapper.builder().build().readTree(body.get()).get("input");
        assertThat(sent.get("stageId").asString()).isEqualTo(stageId.toString());
        assertThat(sent.get("total").decimalValue()).isEqualByComparingTo("82.5");
        assertThat(sent.get("areas").get("의사소통능력").asInt()).isEqualTo(80);
        assertThat(sent.get("areas").has("수리능력")).isTrue();
        assertThat(sent.get("areas").get("수리능력").isNull()).isTrue();
        assertThat(sent.get("submission").isNull()).isTrue();
        assertThat(sent.get("note").asString()).isEqualTo("코드 구조 설명이 명확했음");
        assertThat(result).isEqualTo(new AssessmentAgent.AnalyzeResult("DONE", 2, 1));
    }
}
