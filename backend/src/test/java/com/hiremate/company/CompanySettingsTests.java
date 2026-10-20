package com.hiremate.company;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

class CompanySettingsTests extends IntegrationTest {

    @Test
    @DisplayName("회사 소개를 저장하고 다시 불러온다")
    void savesProfile() throws Exception {
        TestApi hr = newHr();
        JsonNode empty = json(expect(hr.get("/api/companies/me/profile"), 200));
        assertThat(empty.path("name").asString()).isEqualTo("테스트 기업");
        assertThat(empty.path("talents").size()).isZero();

        expect(hr.put("/api/companies/me/profile", Map.of(
                "intro", "결제 인프라를 만드는 핀테크 기업이에요.",
                "culture", "작은 팀이 스스로 정해요.",
                "talents", List.of(Map.of("title", "고객 신뢰를 최우선으로", "description", "책임감")),
                "benefits", List.of("유연 근무", "점심 식대"))), 200);

        JsonNode saved = json(expect(hr.get("/api/companies/me/profile"), 200));
        assertThat(saved.path("intro").asString()).isEqualTo("결제 인프라를 만드는 핀테크 기업이에요.");
        assertThat(saved.path("talents").get(0).path("title").asString()).isEqualTo("고객 신뢰를 최우선으로");
        assertThat(saved.path("benefits").size()).isEqualTo(2);
    }

    @Test
    @DisplayName("채용 공고 설정은 섹션 순서와 함께 저장한다")
    void savesPostingSettings() throws Exception {
        TestApi hr = newHr();
        expect(hr.put("/api/companies/me/posting-settings", Map.of(
                "writingStyle", "짧고 친근한 존댓말", "requiredNotices", List.of("채용 일정은 바뀔 수 있어요."))), 200);

        JsonNode settings = json(expect(hr.get("/api/companies/me/posting-settings"), 200));
        assertThat(settings.path("sections").get(0).asString()).isEqualTo("회사 소개");
        assertThat(settings.path("writingStyle").asString()).isEqualTo("짧고 친근한 존댓말");
        assertThat(settings.path("requiredNotices").get(0).asString()).isEqualTo("채용 일정은 바뀔 수 있어요.");
    }

    @Test
    @DisplayName("안내 메일 양식은 기본 양식 네 가지에서 시작하고 유형별로 바꾼다")
    void updatesNoticeTemplates() throws Exception {
        TestApi hr = newHr();
        JsonNode defaults = json(expect(hr.get("/api/companies/me/notice-templates"), 200));
        assertThat(defaults.size()).isEqualTo(4);
        assertThat(defaults.get(0).path("type").asString()).isEqualTo("NEXT_STAGE");

        expect(hr.put("/api/companies/me/notice-templates/REJECT", Map.of("subject", "[{회사명}] 결과 안내",
                "greeting", "{지원자명}님", "aiGuide", "결과", "closing", "드림", "requiredText", "발신 전용")), 200);

        JsonNode updated = json(expect(hr.get("/api/companies/me/notice-templates"), 200));
        assertThat(updated.get(1).path("subject").asString()).isEqualTo("[{회사명}] 결과 안내");
        assertThat(updated.get(0).path("subject").asString()).isEqualTo("[{회사명}] {전형명} 결과 안내");
    }

    @Test
    @DisplayName("참고 자료는 PDF만 올리고 내려받고 지운다")
    void managesReferencePdfs() throws Exception {
        TestApi hr = newHr();
        byte[] pdf = "%PDF-1.4 company".getBytes(StandardCharsets.UTF_8);
        JsonNode uploaded = json(expect(hr.multipart("/api/companies/me/files?category=INTRO",
                Map.of("file", new TestApi.FilePart("회사소개서.pdf", "application/pdf", pdf))), 201));
        String fileId = uploaded.path("fileId").asString();

        JsonNode list = json(expect(hr.get("/api/companies/me/files?category=INTRO"), 200));
        assertThat(list.get(0).path("name").asString()).isEqualTo("회사소개서.pdf");
        assertThat(hr.getBytes("/api/companies/me/files/" + fileId + "/content").body()).isEqualTo(pdf);

        expect(hr.multipart("/api/companies/me/files?category=INTRO",
                Map.of("file", new TestApi.FilePart("a.pdf", "application/pdf", new byte[] {1, 2, 3}))), 400);

        expect(hr.delete("/api/companies/me/files/" + fileId), 204);
        assertThat(json(expect(hr.get("/api/companies/me/files?category=INTRO"), 200)).size()).isZero();
        expect(newHr().get("/api/companies/me/files/" + fileId + "/content"), 404);
    }
}
