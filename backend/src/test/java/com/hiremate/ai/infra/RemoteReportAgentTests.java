package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.ReportInput;
import com.hiremate.report.ReportContent;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteReportAgentTests {

    private static final String RESPONSE = """
            {"summary": "지원자 8명 중 **1명**을 최종 합격으로 결정했어요.", "applicantCount": 8, "finalCount": 1,
             "stages": [{"name": "서류 전형", "target": 8, "pass": 4, "fail": 4}],
             "finalists": [{"name": "정유민", "reason": "결제 승인 서버를 개선했어요.", "sources": ["이력서 > 경력"]}],
             "notes": []}
            """;

    private final AtomicReference<String> path = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private HttpServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            path.set(exchange.getRequestURI().getPath());
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] response = RESPONSE.getBytes(StandardCharsets.UTF_8);
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
    @DisplayName("ai 서버의 /agents/report/write에 input을 보내고 ReportContent를 받는다")
    void postsInputAndReadsReport() {
        String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
        RemoteReportAgent agent = new RemoteReportAgent(
                new AiServerClient(WebClient.builder(), baseUrl, Duration.ofSeconds(5)));
        ReportInput input = new ReportInput("결제 플랫폼 백엔드 개발자", 8,
                List.of(new ReportContent.ReportStage("서류 전형", 8, 4, 4)),
                List.of(new ReportInput.FinalistInput("정유민",
                        List.of(new CandidateAnalysis.Finding("결제 승인 서버 응답 시간을 줄였다", "이력서 > 경력")),
                        List.of("장애 대응 경험을 설명함"))),
                List.of(1L));

        ReportContent report = agent.write(input);

        assertThat(path.get()).isEqualTo("/agents/report/write");
        JsonNode sent = JsonMapper.builder().build().readTree(body.get());
        assertThat(sent.get("input").get("applicantCount").asLong()).isEqualTo(8);
        assertThat(sent.get("input").get("stages").get(0).get("pass").asLong()).isEqualTo(4);
        assertThat(sent.get("input").get("finalists").get(0).get("notable").get(0).get("source").asString())
                .isEqualTo("이력서 > 경력");
        assertThat(report.finalCount()).isEqualTo(1);
        assertThat(report.stages()).containsExactly(new ReportContent.ReportStage("서류 전형", 8, 4, 4));
        assertThat(report.finalists().getFirst().sources()).containsExactly("이력서 > 경력");
    }
}
