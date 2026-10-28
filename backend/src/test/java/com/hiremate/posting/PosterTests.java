package com.hiremate.posting;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

class PosterTests extends IntegrationTest {

    @Test
    @DisplayName("기업 템플릿을 추가하고 기본값 저장에도 보존하며 다른 기업과 공유하지 않는다")
    void companyTemplatesAreScopedAndPreserved() throws Exception {
        TestApi hr = newHr();
        Map<String, Object> template = Map.of("name", "여름 채용", "template", "NATURAL", "color", "#167ca7");
        JsonNode added = json(expect(hr.post("/api/companies/me/poster-brand/templates", template), 200));
        assertThat(added.path("templates").size()).isEqualTo(1);
        assertThat(added.path("templates").get(0).path("name").asString()).isEqualTo("여름 채용");
        expect(hr.post("/api/companies/me/poster-brand/templates", template), 409);
        expect(hr.put("/api/companies/me/poster-brand", Map.of("template", "CLASSIC", "mood", "TRUST",
                "color", "#2459a6", "decoration", 1)), 200);
        JsonNode saved = json(expect(hr.get("/api/companies/me/poster-brand"), 200));
        assertThat(saved.path("templates")).isEqualTo(added.path("templates"));
        assertThat(json(expect(newHr().get("/api/companies/me/poster-brand"), 200))
                .path("templates").size()).isZero();
        expect(hr.post("/api/companies/me/poster-brand/templates", Map.of("name", " ",
                "template", "CLASSIC", "color", "#2459a6")), 400);
    }

    @Test
    @DisplayName("기업 기본 디자인을 새 공고에 복사하고, AI 추천은 적용 전까지 공고를 바꾸지 않는다")
    void defaultsAreCopiedAndRecommendationsDoNotWrite() throws Exception {
        TestApi hr = newHr();
        expect(hr.put("/api/companies/me/poster-brand", Map.of("template", "PREMIUM", "mood", "PREMIUM",
                "color", "#79634b", "decoration", 0)), 200);
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        assertThat(draft.path("poster").path("template").asString()).isEqualTo("PREMIUM");
        assertThat(draft.path("poster").path("enabled").asBoolean()).isFalse();
        JsonNode result = json(expect(hr.post(base + "/poster/ai-requests", Map.of("message", "더 고급스럽게")), 200));
        assertThat(result.path("recommendations").size()).isEqualTo(2);
        assertThat(json(expect(hr.get(base), 200)).path("poster")).isEqualTo(draft.path("poster"));
        expect(hr.put("/api/companies/me/poster-brand", Map.of("template", "BOLD", "mood", "LIVELY",
                "color", "#6540ae", "decoration", 2)), 200);
        assertThat(json(expect(hr.get(base), 200)).path("poster")).isEqualTo(draft.path("poster"));
    }

    @Test
    @DisplayName("로고를 검증하고 공개 공고로만 제공하며, 게시 후 설정 변경과 삭제에도 게시한 로고를 유지한다")
    void logoIsScopedAndPublishedSnapshotIsStable() throws Exception {
        TestApi hr = newHr();
        BufferedImage logo = new BufferedImage(10, 10, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < 10; y++) {
            for (int x = 0; x < 10; x++) {
                logo.setRGB(x, y, new Color(30, 100, 170).getRGB());
            }
        }
        ByteArrayOutputStream image = new ByteArrayOutputStream();
        ImageIO.write(logo, "png", image);
        byte[] bytes = image.toByteArray();
        JsonNode brand = json(expect(hr.multipart("/api/companies/me/poster-brand/logo", Map.of("file",
                new TestApi.FilePart("logo.png", "image/png", bytes))), 200));
        assertThat(brand.path("color").asString()).isNotEqualTo("#2459a6");
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        String publicBase = "/api/public/postings/" + draft.path("postingId").asString();
        PosterDesign design = new PosterDesign(PosterDesign.Template.NATURAL, PosterDesign.Mood.CLEAR,
                brand.path("color").asString(), 1, true, true,
                UUID.fromString(brand.path("logoFileId").asString()));
        expect(hr.put(base + "/poster", design), 200);
        expect(anonymous().get(publicBase + "/poster/logo"), 404);
        expect(newHr().get(base), 404);
        expect(hr.post(base + "/publish", Map.of("openAt", Instant.now().minusSeconds(60).toString(),
                "closeAt", Instant.now().plusSeconds(3600).toString())), 200);
        expect(hr.delete("/api/companies/me/poster-brand/logo"), 200);
        assertThat(anonymous().getBytes(publicBase + "/poster/logo").body()).isEqualTo(bytes);
        assertThat(json(expect(anonymous().get(publicBase), 200)).path("poster").path("mood").asString())
                .isEqualTo("CLEAR");
        expect(hr.put(base + "/poster", design), 409);
        expect(hr.post(base + "/poster/ai-requests", Map.of("message", "바꿔줘")), 409);
    }

    @Test
    @DisplayName("없는 로고 ID, 잘못된 디자인과 이미지 파일을 거부한다")
    void invalidDesignAndForeignLogoAreRejected() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        PosterDesign design = new PosterDesign(PosterDesign.Template.CLASSIC, PosterDesign.Mood.TRUST,
                "#2459a6", 1, true, true, UUID.randomUUID());
        expect(hr.put(base + "/poster", design), 400);
        expect(hr.post(base + "/poster/ai-requests", Map.of("message", "고급스럽게", "design", design)), 400);
        expect(hr.put(base + "/poster", Map.of("template", "INVALID", "mood", "CLEAR", "color", "red")), 400);
        expect(hr.multipart("/api/companies/me/poster-brand/logo", Map.of("file",
                new TestApi.FilePart("logo.png", "image/png", new byte[] {1, 2, 3}))), 400);
        Map<String, Object> turn = Map.of("role", "USER", "text", "이전 추천", "recommendations", List.of());
        expect(hr.post(base + "/poster/ai-requests", Map.of("message", "두 번째로",
                "history", Collections.nCopies(13, turn))), 400);
        expect(hr.post(base + "/poster/ai-requests", Map.of("message", "두 번째로",
                "history", Collections.singletonList(null))), 400);
    }

    @Test
    @DisplayName("포스터 API 계약을 OpenAPI에 공개한다")
    void openApiIncludesPosterContracts() throws Exception {
        String body = expect(newHr().get("/v3/api-docs"), 200).body();
        assertThat(body).contains("PosterDesign", "/api/companies/me/poster-brand",
                "/api/recruitments/{recruitmentId}/posting/poster");
        Files.writeString(Path.of("build", "openapi.json"), body);
    }
}
