package com.hiremate.dashboard;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

class DashboardTests extends IntegrationTest {

    @Test
    @DisplayName("대시보드는 상태별 인원과 채용별 전형 흐름을 보여 주고, 다른 기업의 채용은 보이지 않는다")
    void listsRecruitmentsWithWorkflow() throws Exception {
        TestApi hr = newHr();
        expect(hr.post("/api/recruitments", null), 201);
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        expect(anonymous().multipart(posting.applyPath(), TestFixtures.form("a@example.com", false)), 201);

        JsonNode dashboard = json(expect(hr.get("/api/recruitments"), 200));
        assertThat(dashboard.path("counts").path("all").asLong()).isEqualTo(2);
        assertThat(dashboard.path("counts").path("draft").asLong()).isEqualTo(1);
        assertThat(dashboard.path("counts").path("published").asLong()).isEqualTo(1);

        JsonNode published = json(expect(hr.get("/api/recruitments?status=PUBLISHED"), 200)).path("items").get(0);
        assertThat(published.path("applicantCount").asLong()).isEqualTo(1);
        assertThat(published.path("steps").size()).isEqualTo(2);

        expect(hr.post("/api/recruitments/" + posting.recruitmentId() + "/posting/close", null), 200);
        JsonNode progress = json(expect(hr.get("/api/recruitments?query=백엔드"), 200)).path("items").get(0);
        assertThat(progress.path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(progress.path("steps").get(0).path("targetCount").asLong()).isEqualTo(1);

        assertThat(json(expect(newHr().get("/api/recruitments"), 200)).path("counts").path("all").asLong()).isZero();
    }
}
