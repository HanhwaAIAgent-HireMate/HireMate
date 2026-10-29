package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.ChatApplied;
import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.ChatProgress;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.http.client.reactive.MockClientHttpRequest;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class RemoteRootAgentTests {

    private static final Path CONTRACT_DIR = Path.of("..", "contract");
    private static final JsonMapper MAPPER = JsonMapper.builder().build();

    @Test
    @DisplayName("ChatContext를 context 키로 /agents/root/plan에 보내고 ChatPlan을 받는다")
    void sendsContextAndReadsPlan() throws IOException {
        AtomicReference<ClientRequest> sent = new AtomicReference<>();
        String plan = MAPPER.readTree(Files.readString(CONTRACT_DIR.resolve("ChatPlan.json"))).toString();
        AiServerClient client = new AiServerClient(WebClient.builder().exchangeFunction(request -> {
            sent.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_EVENT_STREAM_VALUE)
                    .body("event:status\ndata:{\"text\":\"요청을 확인하고 있어요\"}\n\nevent:done\ndata:" + plan + "\n\n")
                    .build());
        }), "http://ai.test", Duration.ofSeconds(1), MAPPER);
        List<String> statuses = new ArrayList<>();
        ChatContext context = MAPPER.readValue(Files.readString(CONTRACT_DIR.resolve("ChatContext.json")),
                ChatContext.class);

        ChatPlan result = new RemoteRootAgent(client).plan(context, new ChatProgress() {
            @Override
            public void status(String text) {
                statuses.add(text);
            }

            @Override
            public void item(ChatItem item) {
            }
        });

        assertThat(sent.get().url()).hasToString("http://ai.test/agents/root/plan");
        JsonNode body = MAPPER.readTree(bodyOf(sent.get()));
        assertThat(body.propertyNames()).containsExactly("context");
        assertThat(body.path("context").path("stageId").asString()).isEqualTo(context.stageId().toString());
        assertThat(body.path("context").path("recruitmentId").asString())
                .isEqualTo(context.recruitmentId().toString());
        assertThat(result.edit()).isEqualTo(ChatPlan.EditAction.REMOVE);
        assertThat(statuses).containsExactly("요청을 확인하고 있어요");
    }

    @Test
    @DisplayName("대화 기록은 threadId로 /agents/root/history에서 받고, 탭 대화방 지우기는 forget으로 보낸다")
    void historyAndForget() throws IOException {
        List<ClientRequest> sent = new ArrayList<>();
        String turn = Files.readString(CONTRACT_DIR.resolve("ChatHistoryTurn.json"));
        AiServerClient client = new AiServerClient(WebClient.builder().exchangeFunction(request -> {
            sent.add(request);
            String body = request.url().getPath().endsWith("/history") ? "[" + turn + "]" : "{\"deleted\":1}";
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(body)
                    .build());
        }), "http://ai.test", Duration.ofSeconds(1), MAPPER);
        RemoteRootAgent agent = new RemoteRootAgent(client);

        List<ChatHistoryTurn> history = agent.history("c:s:t");
        agent.forget("c:s:t");

        assertThat(history).hasSize(1);
        assertThat(history.getFirst().total()).isEqualTo(2);
        assertThat(history.getFirst().mentions()).hasSize(1);
        assertThat(history.getFirst().steps()).startsWith("요청을 확인하고 있어요");
        assertThat(history.getFirst().seconds()).isEqualTo(6);
        assertThat(sent).extracting(request -> request.url().getPath())
                .containsExactly("/agents/root/history", "/agents/root/forget");
        assertThat(MAPPER.readTree(bodyOf(sent.get(0))).path("threadId").asString()).isEqualTo("c:s:t");
        assertThat(MAPPER.readTree(bodyOf(sent.get(1))).path("threadId").asString()).isEqualTo("c:s:t");
    }

    @Test
    @DisplayName("실제 반영한 계획과 원본 계획을 applied 키로 /agents/root/applied에 보낸다")
    void sendsAppliedPlan() throws IOException {
        AtomicReference<ClientRequest> sent = new AtomicReference<>();
        AiServerClient client = new AiServerClient(WebClient.builder().exchangeFunction(request -> {
            sent.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body("{\"applied\":true}").build());
        }), "http://ai.test", Duration.ofSeconds(1), MAPPER);
        ChatPlan plan = MAPPER.readValue(Files.readString(CONTRACT_DIR.resolve("ChatPlan.json")), ChatPlan.class);
        ChatApplied applied = new ChatApplied("company:stage:member", "이 지원자 빼줘", plan, plan);

        new RemoteRootAgent(client).applied(applied);

        assertThat(sent.get()).isNotNull();
        assertThat(sent.get().url()).hasToString("http://ai.test/agents/root/applied");
        JsonNode body = MAPPER.readTree(bodyOf(sent.get()));
        assertThat(body.propertyNames()).containsExactly("applied");
        assertThat(body.path("applied")).isEqualTo(MAPPER.valueToTree(applied));
    }

    private static String bodyOf(ClientRequest request) {
        MockClientHttpRequest written = new MockClientHttpRequest(HttpMethod.POST, URI.create("http://ai.test"));
        request.writeTo(written, ExchangeStrategies.withDefaults()).block();
        return written.getBodyAsString().block();
    }
}
