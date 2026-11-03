package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.net.http.HttpResponse;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.JsonNode;

/**
 * 면접관 의견(추천도 + 이유). 배정된 면접관이 내 면접을 마친 뒤에 쓰고, 다른 면접관의 의견은 내 의견을 저장한 뒤에
 * 보인다. HR은 언제나 모든 의견을 본다. 결정은 HR이 하고, 의견은 AI에 넘기지 않는다.
 */
class InterviewOpinionTests extends IntegrationTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    @DisplayName("다른 면접관의 의견은 내 의견을 저장하기 전에는 제출 여부만 보이고, HR은 모두 본다")
    void opinionsStayHiddenUntilOwnIsSaved() throws Exception {
        Room room = ended();

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
        Room room = ended();
        String mine = room.opinions() + "/me";

        expect(room.kim().put(mine, Map.of("recommendation", "RECOMMEND", "comment", " ")), 400);
        JsonNode first = json(expect(room.kim().put(mine,
                Map.of("recommendation", "RECOMMEND", "comment", "처음 의견")), 200));
        assertThat(entry(first, "PRACTICAL").path("edited").asBoolean()).isFalse();
        assertThat(entry(first, "PRACTICAL").path("updatedAt").isNull()).isFalse();
        JsonNode firstRead = json(expect(room.kim().get(room.opinions()), 200));
        assertThat(entry(firstRead, "PRACTICAL").path("edited").asBoolean()).isFalse();
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

    @Test
    @DisplayName("의견은 내 면접을 마친 뒤에 쓰고, 불참한 지원자에게는 쓰지 않는다")
    void opinionsWaitForOwnInterviewEnd() throws Exception {
        Room room = room();
        String mine = room.opinions() + "/me";
        Map<String, String> opinion = Map.of("recommendation", "RECOMMEND", "comment", "면접 전 의견");

        assertThat(code(room.kim().put(mine, opinion))).isEqualTo("INTERVIEW_NOT_ENDED");
        start(room);
        assertThat(code(room.kim().put(mine, opinion))).isEqualTo("INTERVIEW_NOT_ENDED");
        // 먼저 마친 면접관은 상대가 아직 면접 중이어도 의견을 쓴다
        expect(room.kim().post(room.session() + "/end", null), 200);
        expect(room.kim().put(mine, opinion), 200);
        assertThat(code(room.people().put(mine, opinion))).isEqualTo("INTERVIEW_NOT_ENDED");

        Room absent = room();
        expect(absent.kim().post(absent.session() + "/absent", null), 200);
        assertThat(code(absent.kim().put(absent.opinions() + "/me", opinion))).isEqualTo("INTERVIEW_ABSENT");
    }

    @Test
    @DisplayName("HR 알림은 면접이 끝나면 종료를, 두 면접관 의견이 모두 들어오면 의견 완료를 알린다")
    void noticesTellHrWhenInterviewsEndAndOpinionsArrive() throws Exception {
        Room room = ended();
        String notices = "/api/companies/current/interviews/notices";
        assertThat(kinds(json(expect(room.hr().get(notices), 200)))).containsExactly("ENDED", "STARTED");

        expect(room.kim().put(room.opinions() + "/me", Map.of("recommendation", "RECOMMEND",
                "comment", "설계 판단 근거가 분명함")), 200);
        assertThat(kinds(json(expect(room.hr().get(notices), 200)))).containsExactly("ENDED", "STARTED");
        expect(room.people().put(room.opinions() + "/me", Map.of("recommendation", "HOLD",
                "comment", "협업 범위는 더 확인 필요")), 200);
        JsonNode done = json(expect(room.hr().get(notices), 200));
        assertThat(kinds(done)).containsExactly("OPINIONS_DONE", "ENDED", "STARTED");
        assertThat(done.get(0).path("stageId").asString()).isEqualTo(room.interview().stageId().toString());
        assertThat(done.get(0).path("applicantNames")).hasSize(1);
        // 의견을 고쳐도 다시 알리지 않는다 (처음 저장한 때가 기준)
        String at = done.get(0).path("at").asString();
        expect(room.people().put(room.opinions() + "/me", Map.of("recommendation", "RECOMMEND",
                "comment", "다시 보니 협업 범위도 분명함")), 200);
        assertThat(json(expect(room.hr().get(notices), 200)).get(0).path("at").asString()).isEqualTo(at);
    }

    private static List<String> kinds(JsonNode notices) {
        return notices.valueStream().map(notice -> notice.path("kind").asString()).toList();
    }

    /** kim은 실무 면접관, people은 인사 면접관이다. */
    private record Room(Interview interview, TestApi kim, TestApi people) {

        TestApi hr() {
            return interview.hr();
        }

        String session() {
            return "/api/interviewer/sessions/" + interview.stageId() + "/" + interview.applicationId();
        }

        String opinions() {
            return session() + "/opinions";
        }
    }

    /** 두 면접관이 모두 마친 면접. */
    private Room ended() throws Exception {
        Room room = room();
        start(room);
        expect(room.kim().post(room.session() + "/end", null), 200);
        expect(room.people().post(room.session() + "/end", null), 200);
        return room;
    }

    /** 두 면접관이 [준비 완료]를 눌러 면접을 시작한다. */
    private static void start(Room room) throws Exception {
        expect(room.kim().post(room.session() + "/ready", null), 200);
        expect(room.people().post(room.session() + "/ready", null), 200);
    }

    /** 인사는 면접관 최인사, 실무는 면접관 김지민으로 배정하고 일시를 정한 면접. 미리 만드는 질문이 다 들어온 뒤다. */
    private Room room() throws Exception {
        Interview interview = interviewStage();
        TestApi kim = newInterviewer(interview.hr(), "김지민");
        TestApi people = newInterviewer(interview.hr(), "최인사");
        Map<String, Object> body = new HashMap<>();
        body.put("hrMemberId", people.memberId().toString());
        body.put("practicalMemberId", kim.memberId().toString());
        body.put("expectedVersion", null);
        expect(interview.hr().put(interview.stage() + "/interview/assignment", body), 200);
        Map<String, Object> schedule = new HashMap<>();
        schedule.put("scheduledAt", "2026-11-20T05:00:00Z");
        schedule.put("interviewers", "");
        expect(interview.hr().put(interview.candidate() + "/interview/schedule", schedule), 200);
        long deadline = System.currentTimeMillis() + 15_000;
        while (System.currentTimeMillis() < deadline && (json(expect(interview.hr().get(interview.candidate()
                + "/interview/preparing"), 200)).path("preparing").asBoolean() || json(expect(interview.hr()
                .get(interview.candidate() + "/interview"), 200)).path("questions").isEmpty())) {
            Thread.sleep(200);
        }
        return new Room(interview, kim, people);
    }

    private static String code(HttpResponse<String> response) {
        return json(expect(response, 409)).path("code").asString();
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
