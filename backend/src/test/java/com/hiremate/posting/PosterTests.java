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
    @DisplayName("외부 포스터 요소와 출처를 저장하고 게시 후에도 그대로 조회한다")
    void externalCanvasSurvivesPublishing() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        String canvas = "{\"width\":600,\"height\":900,\"objects\":[],\"source\":{\"license\":\"CC0 1.0\"}}";
        PosterDesign design = new PosterDesign(PosterDesign.Template.CLASSIC, PosterDesign.Mood.TRUST,
                "#2459a6", 1, true, false, null, PosterDesign.BackgroundStyle.SOLID,
                Map.of(), List.of(), canvas, "새로운 도전을 함께 시작합니다");
        JsonNode saved = json(expect(hr.put(base + "/poster", design), 200));
        assertThat(saved.path("poster").path("canvasJson").asString()).isEqualTo(canvas);
        assertThat(saved.path("poster").path("tagline").asString()).isEqualTo(design.tagline());
        expect(hr.post(base + "/publish", Map.of("openAt", Instant.now().minusSeconds(60).toString(),
                "closeAt", Instant.now().plusSeconds(3600).toString())), 200);
        JsonNode published = json(expect(anonymous().get("/api/public/postings/"
                + draft.path("postingId").asString()), 200));
        assertThat(published.path("poster").path("canvasJson").asString()).isEqualTo(canvas);
        assertThat(published.path("poster").path("tagline").asString()).isEqualTo(design.tagline());
        expect(hr.put(base + "/poster", design), 409);
    }

    @Test
    @DisplayName("포스터 아이콘은 전형을 바꾸지 않고 디자인에만 저장한다")
    void posterIconsDoNotChangeStages() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        expect(hr.put(base + "/stages", Map.of("stages", List.of(
                Map.of("name", "실무면접", "type", "INTERVIEW")))), 200);
        JsonNode before = json(expect(hr.get(base), 200)).path("stages");
        Map<String, Object> design = new java.util.HashMap<>(Map.of("template", "CLASSIC", "mood", "TRUST",
                "color", "#2459a6", "decoration", 1, "enabled", true, "showLogo", false,
                "stageIcons", Map.of("실무면접", "USERS"), "readableSections", List.of(2)));
        JsonNode saved = json(expect(hr.put(base + "/poster", design), 200));
        assertThat(saved.path("poster").path("stageIcons").path("실무면접").asString()).isEqualTo("USERS");
        assertThat(saved.path("stages")).isEqualTo(before);
        assertThat(saved.path("poster").path("readableSections").get(0).asInt()).isEqualTo(2);
        design.put("stageIcons", Map.of("없는 전형", "HEALTH"));
        expect(hr.put(base + "/poster", design), 400);
    }

    @Test
    @DisplayName("직무별 모집 표와 전형 아이콘을 저장하고 게시한 공고에도 유지한다")
    void rolesAndStageIconsSurvivePublishing() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String base = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        List<PostingRole> roles = List.of("백엔드", "인사", "생산관리").stream()
                .map(name -> new PostingRole(name, "신입", List.of(name + " 업무"),
                        List.of("직무 기초 지식"), List.of())).toList();
        PostingContent content = new PostingContent("신입 공개채용", "여러 직무", "정규직", "신입", "서울", "",
                List.of(), List.of(), List.of(), List.of(), null, "", "", "", "", roles);
        expect(hr.put(base, content), 200);
        expect(hr.put(base + "/stages", Map.of("stages", List.of(Map.of("name", "코딩테스트",
                "type", "ASSESSMENT", "icon", "CODE")))), 200);
        JsonNode saved = json(expect(hr.get(base), 200));
        assertThat(saved.path("content").path("roles").size()).isEqualTo(3);
        assertThat(saved.path("stages").get(0).path("icon").asString()).isEqualTo("CODE");
        expect(hr.put(base + "/stages", Map.of("stages", List.of(Map.of("name", "코딩테스트",
                "type", "ASSESSMENT", "icon", "ARBITRARY_HTML")))), 400);
        expect(hr.post(base + "/publish", Map.of("openAt", Instant.now().minusSeconds(60).toString(),
                "closeAt", Instant.now().plusSeconds(3600).toString())), 200);
        JsonNode published = json(expect(anonymous().get("/api/public/postings/"
                + draft.path("postingId").asString()), 200));
        assertThat(published.path("content").path("roles")).isEqualTo(saved.path("content").path("roles"));
        assertThat(published.path("stages").get(0).path("icon").asString()).isEqualTo("CODE");
        expect(hr.put(base, content), 409);
    }

    @Test
    @DisplayName("기업 템플릿을 추가하고 기본값 저장에도 보존하며 다른 기업과 공유하지 않는다")
    void companyTemplatesAreScopedAndPreserved() throws Exception {
        TestApi hr = newHr();
        String canvas = "{\"width\":600,\"height\":850,\"objects\":[]}";
        Map<String, Object> template = Map.of("name", "여름 채용", "template", "NATURAL", "color", "#167ca7",
                "canvasJson", canvas);
        JsonNode added = json(expect(hr.post("/api/companies/me/poster-brand/templates", template), 200));
        assertThat(added.path("templates").size()).isEqualTo(1);
        assertThat(added.path("templates").get(0).path("name").asString()).isEqualTo("여름 채용");
        assertThat(added.path("templates").get(0).path("canvasJson").asString()).isEqualTo(canvas);
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
    @DisplayName("Canva 연결은 HR만 보고 비밀값을 응답하지 않으며 승인 없는 callback은 거부한다")
    void canvaConnectionIsPrivateAndRequiresConsent() throws Exception {
        String path = "/api/companies/me/canva";
        expect(anonymous().get(path), 401);
        TestApi hr = newHr();
        JsonNode state = json(expect(hr.get(path), 200));
        assertThat(state.path("connected").asBoolean()).isFalse();
        assertThat(state.path("tools").size()).isZero();
        assertThat(state.has("clientSecret")).isFalse();
        assertThat(state.has("accessToken")).isFalse();
        expect(hr.post(path + "/verify", null), 409);
        expect(hr.get(path + "/callback?state=forged&code=invalid"), 400);
        expect(hr.delete(path), 204);
    }

    @Test
    @DisplayName("추가한 템플릿만 현재 기업에서 삭제하고 기존 공고 디자인은 보존한다")
    void deleteCustomTemplatePreservesPostingAndOtherCompanies() throws Exception {
        TestApi hr = newHr();
        String path = "/api/companies/me/poster-brand/templates";
        JsonNode brand = json(expect(hr.post(path, Map.of("name", "삭제 테스트", "template", "NATURAL",
                "color", "#167ca7")), 200));
        String id = brand.path("templates").get(0).path("id").asString();
        JsonNode posting = json(expect(hr.post("/api/recruitments", null), 201));
        String postingPath = "/api/recruitments/" + posting.path("recruitmentId").asString() + "/posting";
        PosterDesign design = new PosterDesign(PosterDesign.Template.NATURAL, PosterDesign.Mood.NATURAL,
                "#167ca7", 1, true, false, null);
        JsonNode saved = json(expect(hr.put(postingPath + "/poster", design), 200)).path("poster");
        expect(anonymous().delete(path + "/" + id), 401);
        expect(newHr().delete(path + "/" + id), 404);
        expect(hr.delete(path + "/CLASSIC"), 400);
        JsonNode remaining = json(expect(hr.delete(path + "/" + id), 200));
        assertThat(remaining.path("templates").size()).isZero();
        assertThat(remaining.path("template").asString()).isEqualTo(brand.path("template").asString());
        assertThat(json(expect(hr.get(postingPath), 200)).path("poster")).isEqualTo(saved);
        expect(hr.delete(path + "/" + id), 404);
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
        expect(hr.multipart("/api/companies/me/logo", Map.of("file",
                new TestApi.FilePart("logo.png", "image/png", bytes))), 204);
        JsonNode brand = json(expect(hr.get("/api/companies/me/poster-brand"), 200));
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
        expect(hr.delete("/api/companies/me/logo"), 204);
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
        expect(hr.multipart("/api/companies/me/logo", Map.of("file",
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
