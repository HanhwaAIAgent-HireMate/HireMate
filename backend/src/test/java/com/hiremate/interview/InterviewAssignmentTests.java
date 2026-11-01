package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

/** 면접 전형마다 인사 · 실무 면접관 계정을 지정하고, 면접관은 지정된 전형을 "내 면접"으로 본다. */
class InterviewAssignmentTests extends IntegrationTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    @DisplayName("HR이 담당별로 면접관을 지정하면 그 면접관의 내 면접 목록에 전형과 담당이 보인다")
    void assignsInterviewersAndListsMyInterviews() throws Exception {
        Interview interview = interviewStage();
        TestApi hr = interview.hr();
        TestApi kim = newInterviewer(hr, "김지민");
        TestApi lee = newInterviewer(hr, "이서연");

        JsonNode saved = json(expect(hr.put(interview.stage() + "/interviewers", Map.of("slots", List.of(
                Map.of("role", "HR", "memberId", hr.memberId().toString()),
                Map.of("role", "PRACTICAL", "memberId", kim.memberId().toString())))), 200));
        assertThat(slot(saved, "HR").path("name").asString()).isEqualTo("최은영");
        assertThat(slot(saved, "PRACTICAL").path("name").asString()).isEqualTo("김지민");
        assertThat(json(expect(hr.get(interview.stage() + "/interviewers"), 200))).isEqualTo(saved);

        JsonNode mine = json(expect(kim.get("/api/interviewer/stages"), 200));
        assertThat(mine).hasSize(1);
        assertThat(mine.get(0).path("stageId").asString()).isEqualTo(interview.stageId().toString());
        assertThat(mine.get(0).path("roles").get(0).asString()).isEqualTo("PRACTICAL");
        assertThat(mine.get(0).path("recruitmentTitle").asString()).isNotBlank();
        assertThat(mine.get(0).path("candidateCount").asLong()).isEqualTo(1);
        assertThat(json(expect(lee.get("/api/interviewer/stages"), 200))).isEmpty();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM activity_logs WHERE action = 'ASSIGN_INTERVIEWERS'"
                + " AND target_id = ?", Long.class, interview.stageId())).isEqualTo(1);

        // 다시 저장하면 담당을 통째로 바꾼다. 비운 담당은 지정이 풀린다
        expect(hr.put(interview.stage() + "/interviewers", Map.of("slots", List.of(
                Map.of("role", "PRACTICAL", "memberId", lee.memberId().toString())))), 200);
        assertThat(json(expect(kim.get("/api/interviewer/stages"), 200))).isEmpty();
        assertThat(json(expect(lee.get("/api/interviewer/stages"), 200))).hasSize(1);
    }

    @Test
    @DisplayName("다른 기업 계정과 면접이 아닌 전형에는 지정할 수 없다")
    void rejectsForeignMembersAndNonInterviewStages() throws Exception {
        Interview interview = interviewStage();
        TestApi other = newHr();

        assertThat(json(expect(interview.hr().put(interview.stage() + "/interviewers", Map.of("slots", List.of(
                Map.of("role", "HR", "memberId", other.memberId().toString())))), 400)).path("code").asString())
                .isEqualTo("MEMBER_NOT_FOUND");
        assertThat(json(expect(interview.hr().put(interview.stage() + "/interviewers", Map.of("slots", List.of(
                Map.of("role", "HR", "memberId", UUID.randomUUID().toString())))), 400)).path("code").asString())
                .isEqualTo("MEMBER_NOT_FOUND");

        String document = json(expect(interview.hr().get(interview.stage()), 200)).path("steps").get(0)
                .path("stageId").asString();
        assertThat(json(expect(interview.hr().put("/api/stages/" + document + "/interviewers",
                Map.of("slots", List.of())), 409)).path("code").asString()).isEqualTo("NOT_INTERVIEW_STAGE");
    }

    private static JsonNode slot(JsonNode interviewers, String role) {
        for (JsonNode slot : interviewers.path("slots")) {
            if (slot.path("role").asString().equals(role)) {
                return slot;
            }
        }
        throw new AssertionError("No slot for " + role + ": " + interviewers);
    }
}
