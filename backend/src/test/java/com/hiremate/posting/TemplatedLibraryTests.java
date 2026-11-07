package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class TemplatedLibraryTests {
    private final JsonMapper json = new JsonMapper();

    @Test
    void registersThenRetrievesOncePerCompanyAndGeneratedSource() {
        List<String> calls = new ArrayList<>();
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            calls.add(request.method() + " " + request.url().getPath());
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json")
                    .body("{\"id\":\"00000000-0000-0000-0000-000000000001\",\"name\":\"새 공고 양식\"}").build());
        }), "test-key", "");
        UUID company = UUID.randomUUID();
        String svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 900'><text>채용</text></svg>";
        var first = library.register(company, "generated:one", "새 공고 양식", svg, 900);
        assertThat(library.register(company, "generated:one", "새 공고 양식", svg, 900)).isEqualTo(first);
        assertThat(first.id()).startsWith("templated:");
        assertThat(calls).containsExactly("POST /v1/template",
                "GET /v1/template/00000000-0000-0000-0000-000000000001",
                "GET /v1/template/00000000-0000-0000-0000-000000000001");
        library.register(UUID.randomUUID(), "generated:one", "새 공고 양식", svg, 900);
        assertThat(calls.stream().filter(call -> call.startsWith("POST"))).hasSize(2);
    }

    @Test
    void retriesRetrievalWithoutCreatingAnotherTemplate() {
        List<String> calls = new ArrayList<>();
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            calls.add(request.method().name());
            if (calls.size() == 2) {
                return Mono.just(ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE).build());
            }
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json")
                    .body("{\"id\":\"00000000-0000-0000-0000-000000000001\"}").build());
        }), "test-key", "");
        UUID company = UUID.randomUUID();
        String svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 900'/>";
        assertThatThrownBy(() -> library.register(company, "generated:one", "양식", svg, 900))
                .isInstanceOf(com.hiremate.global.ApiException.class);
        assertThat(library.register(company, "generated:one", "양식", svg, 900).id())
                .isEqualTo("templated:00000000-0000-0000-0000-000000000001");
        assertThat(calls).containsExactly("POST", "GET", "GET");
    }

    @Test
    void rejectsActiveOrExternalSvgBeforeSendingToProviderAndReportsTemplateLimit() {
        List<String> calls = new ArrayList<>();
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            calls.add(request.method().name());
            return Mono.just(ClientResponse.create(HttpStatus.FORBIDDEN).build());
        }), "test-key", "");
        for (String fragment : List.of("<script/>", "<image href='https://example.com/photo.png'/>",
                "<rect style='fill:url(https://example.com/x)'/>")) {
            assertThatThrownBy(() -> library.register(UUID.randomUUID(), "generated:x", "양식",
                    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 900'>"
                            + fragment + "</svg>", 900)).isInstanceOf(com.hiremate.global.ApiException.class);
        }
        assertThat(calls).isEmpty();
        assertThatThrownBy(() -> library.register(UUID.randomUUID(), "generated:x", "양식",
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 900'/>", 900))
                .isInstanceOfSatisfying(com.hiremate.global.ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo("TEMPLATED_TEMPLATE_LIMIT"));
    }

    @Test
    void returnsThreeDistinctRelevantThemesAndRejectsUnsupportedPhotos() {
        List<JsonNode> rows = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            rows.add(template(i, "recruitment theme " + i, "shape"));
        }
        rows.add(template(8, "recruitment theme 0", "shape"));
        rows.add(template(9, "recruitment photo", "image"));
        assertThat(TemplatedLibrary.candidates(rows, "recruitment")).hasSize(3)
                .extracting(PosterProposal.FreeTemplate::name).doesNotHaveDuplicates();
        assertThat(TemplatedLibrary.candidates(rows, "unavailable")).isEmpty();
        assertThat(TemplatedLibrary.preview(template(9, "photo", "image"))).isNull();
    }

    @Test
    void excludesSameLayoutEvenWhenIdNameAndColorDiffer() {
        JsonNode first = template(1, "recruitment original", "shape");
        JsonNode clone = json.readTree(first.toString().replace("original", "clone")
                .replace("000000000001", "000000000009").replace("#082858", "#ff8800"));
        assertThat(TemplatedLibrary.candidates(List.of(first, clone), "recruitment")).hasSize(1);
    }

    @Test
    void reconstructsSafePreviewWithoutExecutingExternalHtmlOrUrls() {
        JsonNode row = json.readTree("""
                {"width":1080,"height":2400,"background":"url(https://evil.example)","layers":[
                  {"type":"shape","x":0,"y":0,"width":1080,"height":860,"fill":"#082858"},
                  {"type":"text","x":80,"y":910,"font_size":"32px","color":"#ffffff",
                   "text":"<script>secret</script><img src=x onerror=alert(1)>회사 소개 & 안내"}
                ]}
                """);
        assertThat(TemplatedLibrary.preview(row)).contains("data-body-top=\"860.0\"", "회사 소개 &amp; 안내")
                .doesNotContain("<script", "<img", "onerror", "evil.example");
    }

    private JsonNode template(int number, String name, String type) {
        return json.readTree("""
                {"id":"00000000-0000-0000-0000-%012d","name":"%s","width":600,"height":1200,
                 "layers":[{"type":"%s","x":0,"y":0,"width":600,"height":%d,"fill":"#082858"}]}
                """.formatted(number, name, type, 300 + number * 20));
    }
}
