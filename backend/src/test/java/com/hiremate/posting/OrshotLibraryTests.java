package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.global.ApiException;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Set;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.client.reactive.MockClientHttpRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class OrshotLibraryTests {
    @Test
    void nativePhotoRenderHidesOnlyCornerDotsAndPreservesTheBadgeAndAnimation() throws Exception {
        ByteArrayOutputStream image = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(600, 389, BufferedImage.TYPE_INT_RGB), "jpg", image);
        String background = "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(image.toByteArray());
        OrshotLibrary library = new OrshotLibrary(WebClient.builder().exchangeFunction(request -> {
            if (request.url().getPath().endsWith("render")) {
                var written = new MockClientHttpRequest(HttpMethod.POST, URI.create("http://orshot.test"));
                request.writeTo(written, ExchangeStrategies.withDefaults()).block();
                String body = written.getBodyAsString().block();
                assertThat(body).contains("\"hm_corner_dots.opacity\":0", "\"headline\":\"AX 개발자\"",
                        "\"role_title\":\"AX 개발자 · 경력 1년\"");
                assertThat(body).doesNotContain("videoOptions", "playbackRate", "animation",
                        "role_title.opacity", "hm_role_badge.opacity");
                return Mono.just(json("{\"data\":{\"content\":\"" + background + "\"}}"));
            }
            return Mono.just(json("""
                    {"id":11,"canvas_width":1080,"canvas_height":700,"modifications":[
                    {"key":"hero_photo","type":"imageUrl"},{"key":"headline","type":"text"},
                    {"key":"role_title","type":"text"},{"key":"hm_role_badge","type":"fill"},
                    {"key":"hm_corner_dots","type":"imageUrl"}]}
                    """));
        }), "test-key", "11");
        var posting = org.mockito.Mockito.mock(PostingView.class);
        var content = new PostingContent("AX 개발자", "개발", "정규직", "경력 1년", "서울", "", List.of(),
                List.of(), List.of(), List.of());
        org.mockito.Mockito.when(posting.content()).thenReturn(content);
        library.renderOriginal(11, posting);
    }

    @Test
    void originalDimensionsAndLegacyHeaderPreserveTheNativeAspectRatio() throws Exception {
        BufferedImage source = new BufferedImage(1200, 2628, BufferedImage.TYPE_INT_RGB);
        var graphics = source.createGraphics();
        graphics.setColor(new java.awt.Color(139, 50, 190));
        graphics.fillRect(0, 0, 1200, 778);
        graphics.setColor(java.awt.Color.WHITE);
        graphics.fillRect(0, 778, 1200, 1850);
        graphics.dispose();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ImageIO.write(source, "jpg", output);
        String image = OrshotLibrary.scaledOriginal("data:image/jpeg;base64,"
                + Base64.getEncoder().encodeToString(output.toByteArray()));
        assertThat(OrshotLibrary.originalHeight(image)).isEqualTo(1314);
        var header = OrshotLibrary.legacyHeader(image);
        assertThat(header.width()).isEqualTo(600);
        assertThat(header.height()).isBetween(388, 391);
        assertThat(OrshotLibrary.originalHeight(header.background())).isEqualTo(header.height());
    }

    @Test
    void unavailableApprovedTemplateDoesNotHideAccessibleCandidates() {
        OrshotLibrary library = new OrshotLibrary(WebClient.builder().exchangeFunction(request -> {
            if (request.url().getPath().endsWith("11")) {
                return Mono.just(ClientResponse.create(HttpStatus.FORBIDDEN).build());
            }
            return Mono.just(json("""
                    {"id":12,"name":"Hiring","canvas_width":1080,"canvas_height":1350,
                    "thumbnail_url":"https://storage.orshot.com/test.png"}
                    """));
        }), "test-key", "11,12");
        assertThat(library.search("hiring", Set.of())).extracting(PosterProposal.FreeTemplate::id)
                .containsExactly("orshot:12");
    }

    @Test
    void searchesOnlyApprovedUnappliedTemplatesWithoutRendering() {
        List<String> paths = new ArrayList<>();
        OrshotLibrary library = new OrshotLibrary(WebClient.builder().exchangeFunction(request -> {
            paths.add(request.url().getPath());
            String id = request.url().getPath().substring(request.url().getPath().lastIndexOf('/') + 1);
            return Mono.just(json("""
                    {"id":%s,"name":"Hiring poster %s","canvas_width":1080,"canvas_height":1350,
                    "thumbnail_url":"https://storage.orshot.com/test.png"}
                    """.formatted(id, id)));
        }), "test-key", "11,12,13");
        var candidates = library.search("hiring", Set.of("orshot:11"));
        assertThat(candidates).extracting(PosterProposal.FreeTemplate::id).containsExactly("orshot:12", "orshot:13");
        assertThat(paths).containsExactly("/v1/studio/templates/12", "/v1/studio/templates/13");
        assertThatThrownBy(() -> library.importTemplate(99)).isInstanceOf(ApiException.class)
                .hasMessage("허용된 원본을 선택해 주세요.");
        assertThat(paths).hasSize(2);
    }

    @Test
    void importsTextFreeBackgroundOnlyOnSelectionAndRejectsExternalImageUrls() throws Exception {
        ByteArrayOutputStream image = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(600, 900, BufferedImage.TYPE_INT_RGB), "jpg", image);
        String background = "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(image.toByteArray());
        List<String> paths = new ArrayList<>();
        OrshotLibrary library = new OrshotLibrary(WebClient.builder().exchangeFunction(request -> {
            paths.add(request.url().getPath());
            boolean video = false;
            if (request.url().getPath().endsWith("render")) {
                var written = new MockClientHttpRequest(HttpMethod.POST, URI.create("http://orshot.test"));
                request.writeTo(written, ExchangeStrategies.withDefaults()).block();
                String body = written.getBodyAsString().block();
                assertThat(body).contains("\"width\":600", "\"height\":750", "\"title.opacity\":0");
                assertThat(body).contains("\"cta_bg_color\":\"transparent\"");
                video = body.contains("\"format\":\"mp4\"");
            }
            if (video) {
                return Mono.just(json("{\"data\":{\"content\":\"https://storage.orshot.com/test/render.mp4\"}}"));
            }
            return Mono.just(request.url().getPath().endsWith("render")
                    ? json("{\"data\":{\"content\":\"" + background + "\"}}")
                    : json("""
                            {"id":11,"name":"Photo","canvas_width":1080,"canvas_height":1350,
                            "pages_data":[{"video_thumbnail_url":"https://storage.orshot.com/test/preview.mp4"}],
                            "modifications":[{"key":"title","type":"text"},{"key":"cta_bg_color","type":"fill"}]}
                            """));
        }), "test-key", "11");
        var imported = library.importTemplate(11);
        assertThat(paths).containsExactly("/v1/studio/templates/11", "/v1/studio/render", "/v1/studio/render");
        assertThat(imported.id()).isEqualTo("orshot:11");
        assertThat(imported.width()).isEqualTo(600);
        assertThat(imported.height()).isBetween(260, 480);
        assertThat(imported.background()).startsWith("data:image/jpeg;base64,");
        assertThat(imported.motionUrl()).isEqualTo("https://storage.orshot.com/test/render.mp4");
        assertThat(imported.motionHeight()).isEqualTo(750);
        assertThat(library.importTemplate(11)).isEqualTo(imported);
        assertThat(paths).hasSize(3);
        assertThatThrownBy(() -> OrshotLibrary.compactHeader("https://private.example/image.jpg"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static ClientResponse json(String body) {
        return ClientResponse.create(HttpStatus.OK).header("Content-Type", "application/json").body(body).build();
    }
}
