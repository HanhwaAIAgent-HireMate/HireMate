package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

/**
 * 면접관 의견(추천도 + 이유). 배정된 면접관만 쓰고, 다른 면접관의 의견은 내 의견을 저장한 뒤에 보인다.
 * HR은 언제나 모든 의견을 본다. 결정은 HR이 하고, 의견은 AI에 넘기지 않는다.
 */
class InterviewOpinionTests extends IntegrationTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    @DisplayName("다른 면접관의 의견은 내 의견을 저장하기 전에는 제출 여부만 보이고, HR은 모두 본다")
    void opinionsStayHiddenUntilOwnIsSaved() throws Exception {
        Room room = room();

        JsonNode before = json(expect(room.kim().get(room.opinions()), 200));
        assertThat(before).hasSize(2);
        assertThat(entry(before, "HR").path("submitted").asBoolean()).isFalse();

        expect(room.people().put(room.opinions() + "/me", Map.of("recommendation", "RECOMMEND",
                "comment", "협업 경험을 구체적으로 설명함")), 200);
        JsonNode hidden = entry(json(expect(room.kim().get(room.opinions()), 200)), "HR");
        assertThat(hidden.path("submitted").asBoolean()).isTrue();
        assertThat(hidden.path("recommendation").isNull()).isTrue();
        assertThat(hidden.path("comment").isNull()).isTrue();

        expect(room.kim().put(room.opinions() + "/me", Map.of("recommendation", "HOLD",
                "comment", "설계 판단 범위는 더 확인 필요")), 200);
        JsonNode shown = json(expect(room.kim().get(room.opinions()), 200));
        assertThat(entry(shown, "HR").path("recommendation").asString()).isEqualTo("RECOMMEND");
        assertThat(entry(shown, "PRACTICAL").path("mine").asBoolean()).isTrue();

        JsonNode stage = json(expect(room.hr().get(room.interview().stage() + "/interview/opinions"), 200));
        JsonNode candidate = stage.get(0);
        assertThat(candidate.path("applicationId").asString()).isEqualTo(room.interview().applicationId().toString());
        assertThat(entry(candidate.path("opinions"), "PRACTICAL").path("comment").asString())
                .isEqualTo("설계 판단 범위는 더 확인 필요");
        assertThat(jdbc.queryForObject("SELECT count(*) FROM activity_logs WHERE action = 'SAVE_INTERVIEW_OPINION'",
                Long.class)).isGreaterThanOrEqualTo(2);
    }

    @Test
    @DisplayName("의견을 고치면 수정됨으로 보이고, 이유가 없거나 배정되지 않았거나 결과를 확정했으면 저장하지 않는다")
    void validatesAndMarksEdits() throws Exception {
        Room room = room();
        String mine = room.opinions() + "/me";

        expect(room.kim().put(mine, Map.of("recommendation", "RECOMMEND", "comment", " ")), 400);
        expect(room.kim().put(mine, Map.of("recommendation", "RECOMMEND", "comment", "처음 의견")), 200);
        JsonNode edited = json(expect(room.kim().put(mine, Map.of("recommendation", "NOT_RECOMMEND",
                "comment", "다시 보니 근거가 약함")), 200));
        assertThat(entry(edited, "PRACTICAL").path("edited").asBoolean()).isTrue();

        TestApi stranger = newInterviewer(room.hr(), "이서연");
        assertThat(json(expect(stranger.get(room.opinions()), 403)).path("code").asString())
                .isEqualTo("INTERVIEW_ACCESS_DENIED");

        expect(room.hr().post(room.interview().stage() + "/confirm", null), 200);
        assertThat(json(expect(room.kim().put(mine, Map.of("recommendation", "HOLD", "comment", "늦은 의견")), 409))
                .path("code").asString()).isEqualTo("STAGE_NOT_ACTIVE");
    }

    /** kim은 실무 면접관, people은 인사 면접관이다. */
    private record Room(Interview interview, TestApi kim, TestApi people) {

        TestApi hr() {
            return interview.hr();
        }

        String opinions() {
            return "/api/interviewer/sessions/" + interview.stageId() + "/" + interview.applicationId()
                    + "/opinions";
        }
    }

    /** 인사는 면접관 최인사, 실무는 면접관 김지민으로 배정한 면접. */
    private Room room() throws Exception {
        Interview interview = interviewStage();
        TestApi kim = newInterviewer(interview.hr(), "김지민");
        TestApi people = newInterviewer(interview.hr(), "최인사");
        Map<String, Object> body = new HashMap<>();
        body.put("hrMemberId", people.memberId().toString());
        body.put("practicalMemberId", kim.memberId().toString());
        body.put("expectedVersion", null);
        expect(interview.hr().put(interview.candidate() + "/interview/session", body), 200);
        return new Room(interview, kim, people);
    }

    private static JsonNode entry(JsonNode opinions, String role) {
        for (JsonNode opinion : opinions) {
            if (opinion.path("role").asString().equals(role)) {
                return opinion;
            }
        }
        throw new AssertionError("No opinion for " + role + ": " + opinions);
    }
}
