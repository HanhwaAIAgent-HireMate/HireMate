package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.ChatContext;
import com.hiremate.ai.application.ChatPlan;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
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
        String plan = Files.readString(CONTRACT_DIR.resolve("ChatPlan.json"));
        AiServerClient client = new AiServerClient(WebClient.builder().exchangeFunction(request -> {
            sent.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .body(plan)
                    .build());
        }), "http://ai.test", Duration.ofSeconds(1));
        ChatContext context = MAPPER.readValue(Files.readString(CONTRACT_DIR.resolve("ChatContext.json")),
                ChatContext.class);

        ChatPlan result = new RemoteRootAgent(client).plan(context);

        assertThat(sent.get().url()).hasToString("http://ai.test/agents/root/plan");
        JsonNode body = MAPPER.readTree(bodyOf(sent.get()));
        assertThat(body.propertyNames()).containsExactly("context");
        assertThat(body.path("context").path("stageId").asString()).isEqualTo(context.stageId().toString());
        assertThat(body.path("context").path("recruitmentId").asString())
                .isEqualTo(context.recruitmentId().toString());
        assertThat(result.edit()).isEqualTo(ChatPlan.EditAction.REMOVE);
    }

    private static String bodyOf(ClientRequest request) {
        MockClientHttpRequest written = new MockClientHttpRequest(HttpMethod.POST, URI.create("http://ai.test"));
        request.writeTo(written, ExchangeStrategies.withDefaults()).block();
        return written.getBodyAsString().block();
    }
}
