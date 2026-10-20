package com.hiremate.posting;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

class PostingTests extends IntegrationTest {

    @Test
    @DisplayName("새 채용은 설정의 회사 소개 · 복지 · 필수 안내 문구로 공고 초안을 연다")
    void newRecruitmentStartsFromCompanyTemplate() throws Exception {
        TestApi hr = newHr();
        expect(hr.put("/api/companies/me/profile", Map.of("intro", "핀테크 기업이에요.", "culture", "",
                "talents", List.of(), "benefits", List.of("유연 근무"))), 200);
        expect(hr.put("/api/companies/me/posting-settings",
                Map.of("writingStyle", "", "requiredNotices", List.of("채용 일정은 바뀔 수 있어요."))), 200);

        JsonNode posting = json(expect(hr.post("/api/recruitments", null), 201));

        assertThat(posting.path("status").asString()).isEqualTo("DRAFT");
        assertThat(posting.path("content").path("intro").asString()).isEqualTo("핀테크 기업이에요.");
        assertThat(posting.path("content").path("benefits").get(0).asString()).isEqualTo("유연 근무");
        assertThat(posting.path("notices").get(0).asString()).isEqualTo("채용 일정은 바뀔 수 있어요.");
        assertThat(posting.path("stages").get(0).path("type").asString()).isEqualTo("DOCUMENT");
        assertThat(posting.path("documents").get(2).path("required").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("AI 수정안은 적용해야 공고에 반영되고, 전형 절차는 말한 순서와 종류로 정리된다")
    void aiSuggestionChangesPostingOnlyAfterApply() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";

        JsonNode answer = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 코딩테스트, 1차 면접, 임원 면접 순으로 해줘.")), 200));
        assertThat(answer.path("reply").asString()).contains("평가 1개", "면접 2개");
        assertThat(answer.path("stub").asBoolean()).isTrue();
        JsonNode suggestion = answer.path("posting").path("suggestion");
        assertThat(suggestion.path("stages").size()).isEqualTo(4);
        assertThat(suggestion.path("stages").get(1).path("type").asString()).isEqualTo("ASSESSMENT");
        assertThat(answer.path("posting").path("stages").size()).isEqualTo(1);

        JsonNode applied = json(expect(hr.post(base + "/suggestion/apply", null), 200));
        assertThat(applied.path("stages").get(0).path("name").asString()).isEqualTo("서류 전형");
        assertThat(applied.path("stages").get(3).path("name").asString()).isEqualTo("임원 면접");
        assertThat(applied.path("suggestion").isNull()).isTrue();

        JsonNode unclear = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 컬처핏, 면접 순으로 해줘.")), 200));
        assertThat(unclear.path("reply").asString()).contains("컬처핏");
        assertThat(unclear.path("posting").path("suggestion").isNull()).isTrue();

        expect(hr.post(base + "/ai-requests", Map.of("message", "포트폴리오도 필수로 받아줘.")), 200);
        JsonNode withPortfolio = json(expect(hr.post(base + "/suggestion/apply", null), 200));
        assertThat(withPortfolio.path("documents").get(2).path("required").asBoolean()).isTrue();

        expect(hr.post(base + "/ai-requests", Map.of("message", "우대 사항에 결제·정산 경험을 더 구체적으로 써줘")), 200);
        JsonNode discarded = json(expect(hr.post(base + "/suggestion/discard", null), 200));
        assertThat(discarded.path("content").path("preferred").size()).isZero();
    }

    @Test
    @DisplayName("게시하면 채용 페이지가 열리고 전형 구성은 잠기며, 마감하면 첫 전형이 시작된다")
    void publishOpensCareersPageAndCloseStartsFirstStage() throws Exception {
        TestApi hr = newHr();
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String id = draft.path("recruitmentId").asString();
        String postingId = draft.path("postingId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        JsonNode content = draft.path("content");
        expect(hr.put(base, Map.of("title", "백엔드 개발자 (Java/Spring)", "jobCategory", "개발 › 백엔드",
                "employmentType", "정규직", "career", "경력 3년 이상", "location", "서울 강남구",
                "intro", content.path("intro").asString(), "duties", List.of("결제 시스템 개발"),
                "qualifications", List.of("Java 3년 이상"), "preferred", List.of(), "benefits", List.of())), 200);

        expect(anonymous().get("/api/public/postings/" + postingId), 404);
        Instant now = Instant.now();
        JsonNode published = json(expect(hr.post(base + "/publish", Map.of(
                "openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(7, ChronoUnit.DAYS).toString())), 200));
        assertThat(published.path("status").asString()).isEqualTo("PUBLISHED");

        JsonNode careers = json(expect(anonymous().get("/api/public/postings/" + postingId), 200));
        assertThat(careers.path("state").asString()).isEqualTo("OPEN");
        assertThat(careers.path("content").path("title").asString()).isEqualTo("백엔드 개발자 (Java/Spring)");

        JsonNode locked = json(expect(hr.post(base + "/ai-requests",
                Map.of("message", "전형은 서류, 1차 면접 순으로 해줘")), 200));
        assertThat(locked.path("reply").asString()).contains("게시한 공고");

        JsonNode closed = json(expect(hr.post(base + "/close", null), 200));
        assertThat(closed.path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(json(expect(anonymous().get("/api/public/postings/" + postingId), 200))
                .path("state").asString()).isEqualTo("CLOSED");
        expect(newHr().get(base), 404);
    }
}
