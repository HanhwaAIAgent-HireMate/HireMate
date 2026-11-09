package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class TemplatedLibraryTests {
    private final JsonMapper json = new JsonMapper();

    @Test
    void searchesPublicGalleryWithoutCreatingOrListingAccountTemplates() {
        List<String> calls = new ArrayList<>();
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            calls.add(request.method() + " " + request.url());
            String rows = "[" + template(1, "banking recruitment", "shape") + ","
                    + template(2, "banking recruitment alternate", "shape") + "]";
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json")
                    .body(rows).build());
        }), "test-key", "00000000-0000-0000-0000-000000000009");
        var result = library.searchGallery("banking recruitment",
                Set.of("templated:00000000-0000-0000-0000-000000000001"));
        assertThat(result).extracting(PosterProposal.FreeTemplate::id)
                .containsExactly("templated:00000000-0000-0000-0000-000000000002");
        assertThat(calls).hasSize(2).allSatisfy(call ->
                assertThat(call).startsWith("GET https://api.templated.io/v1/templates/gallery?"));
        assertThat(calls).anySatisfy(call -> assertThat(call).contains("query=banking"));
        assertThat(calls).anySatisfy(call -> assertThat(call).contains("query=recruitment"));
    }

    @Test
    void usesOnlyUnappliedApprovedRecruitmentTemplatesWhenPublicGalleryIsEmpty() {
        String id = "00000000-0000-0000-0000-000000000009";
        List<String> paths = new ArrayList<>();
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            String path = request.url().getPath();
            paths.add(path);
            String body = path.endsWith("/gallery")
                    ? "[]" : template(9, "Editorial Recruitment Poster", "shape").toString();
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json")
                    .body(body).build());
        }), "test-key", id);

        assertThat(library.searchGallery("banking", Set.of())).extracting(PosterProposal.FreeTemplate::id)
                .containsExactly("templated:" + id);
        paths.clear();
        assertThat(library.searchGallery("banking", Set.of("templated:" + id))).isEmpty();
        assertThat(paths).allMatch(path -> path.endsWith("/gallery"));
    }

    @Test
    void usesPublicPhotoBannerWithoutCopyingOriginalTextOrSendingTheKeyToTheAssetHost() throws Exception {
        var photo = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(600, 400, BufferedImage.TYPE_INT_RGB), "png", photo);
        String publicUrl = "https://templated-assets.s3.amazonaws.com/public/pixabay-images/123";
        String row = """
                {"id":"00000000-0000-0000-0000-000000000004","name":"Technology announcement",
                 "width":1200,"height":720,"layers":[
                   {"type":"image","image_url":"%s","x":80,"width":1120,"height":720},
                   {"type":"shape","x":12,"y":34,"width":80,"height":60,"fill":"#133557"},
                   {"type":"text","x":110,"y":150,"width":500,"text":"Original sample copy"}]}
                """.formatted(publicUrl);
        TemplatedLibrary library = new TemplatedLibrary(WebClient.builder().exchangeFunction(request -> {
            if (request.url().toString().equals(publicUrl)) {
                assertThat(request.headers().getFirst("Authorization")).isNull();
                return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "png")
                        .body(reactor.core.publisher.Flux.just(
                                DefaultDataBufferFactory.sharedInstance.wrap(photo.toByteArray()))).build());
            }
            assertThat(request.url().getPath()).endsWith("/gallery");
            return Mono.just(ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json")
                    .body(request.url().getQuery().contains("query=") ? "[]" : "[" + row + "]").build());
        }), "test-key", "00000000-0000-0000-0000-000000000009");

        assertThat(library.searchGallery("backend recruitment", Set.of())).singleElement()
                .satisfies(template -> assertThat(template.svg()).contains("data-templated-artwork=\"true\"",
                        "data-templated-photo=", "data-x=\"80.0\"", "data-x=\"110.0\"", "#133557")
                        .doesNotContain("Original sample copy", publicUrl));
        assertThat(library.searchGallery("backend recruitment",
                Set.of("templated:00000000-0000-0000-0000-000000000004",
                        "templated:00000000-0000-0000-0000-000000000009"))).isEmpty();
    }

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
