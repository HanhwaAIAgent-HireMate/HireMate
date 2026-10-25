package com.hiremate.ai;

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

class CriteriaDraftTests extends IntegrationTest {

    @Test
    @DisplayName("평가 기준 AI 초안은 공고 항목마다 유형 · 판정 기준을 돌려주고 저장하지 않으며, 게시한 뒤에는 쓰지 않는다")
    void draftsCriteriaForPostingItemsUntilPublishing() throws Exception {
        TestApi hr = newHr();
        String id = json(expect(hr.post("/api/recruitments", null), 201)).path("recruitmentId").asString();
        String base = "/api/recruitments/" + id + "/posting";
        expect(hr.put(base, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "",
                "career", "", "location", "", "intro", "", "duties", List.of("결제 승인 · 정산 API 개발"),
                "qualifications", List.of("Java 서버 개발 경력 3년 이상", "RDBMS 스키마 설계와 SQL 작성 경험"),
                "preferred", List.of("결제 도메인 경험"), "benefits", List.of())), 200);

        JsonNode condition = json(expect(hr.post(base + "/criteria/draft",
                Map.of("category", "QUALIFICATION", "text", "Java 서버 개발 경력 3년 이상")), 200));
        assertThat(condition.path("stub").asBoolean()).isTrue();
        assertThat(condition.path("draft").path("criterionType").asString()).isEqualTo("CONDITION");
        assertThat(condition.path("draft").path("partial").isNull()).isTrue();
        JsonNode composite = json(expect(hr.post(base + "/criteria/draft",
                Map.of("category", "QUALIFICATION", "text", "RDBMS 스키마 설계와 SQL 작성 경험")), 200));
        assertThat(composite.path("draft").path("criterionType").asString()).isEqualTo("COMPOSITE");
        assertThat(composite.path("draft").path("partial").asString()).contains("일부만");
        expect(hr.post(base + "/criteria/draft", Map.of("category", "PREFERENCE", "text", "Java 서버 개발 경력 3년 이상")),
                400);

        JsonNode important = json(expect(hr.post(base + "/criteria/important", null), 200));
        assertThat(important.path("advice").path("qualifications").get(0).path("index").asInt()).isZero();
        assertThat(important.path("advice").path("qualifications").get(0).path("duty").asString())
                .isEqualTo("결제 승인 · 정산 API 개발");
        assertThat(important.path("advice").path("preferred").size()).isZero();
        assertThat(json(expect(hr.get(base + "/criteria"), 200)).path("items").get(0).path("saved").asBoolean())
                .isFalse();

        Instant now = Instant.now();
        expect(hr.post(base + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        expect(hr.post(base + "/criteria/draft",
                Map.of("category", "QUALIFICATION", "text", "Java 서버 개발 경력 3년 이상")), 409);
        expect(hr.post(base + "/criteria/important", null), 409);
        expect(newHr().post(base + "/criteria/important", null), 404);
    }
}
