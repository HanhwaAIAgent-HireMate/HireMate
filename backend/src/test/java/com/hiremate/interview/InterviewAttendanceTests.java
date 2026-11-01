package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

/**
 * 면접관 입장과 실시간 알림. 배정된 면접관이 모두 [면접 입장]을 하고 접속 중이어야 면접을 시작한다.
 * 입장 · 시작 같은 변화는 SSE로 다른 면접관 화면과 HR 화면에 바로 알린다.
 */
class InterviewAttendanceTests extends IntegrationTest {

    @Test
    @DisplayName("배정된 면접관이 모두 입장해야 시작할 수 있고, 입장 현황은 면접관과 HR에게 보인다")
    void startWaitsForEveryInterviewer() throws Exception {
        Room room = room();

        JsonNode before = json(expect(room.kim().get(room.session() + "/attendance"), 200));
        assertThat(before.path("stageActive").asBoolean()).isTrue();
        assertThat(before.path("attendees")).hasSize(2);
        assertThat(before.path("attendees").get(0).path("entered").asBoolean()).isFalse();
        assertThat(code(room.kim().post(room.session() + "/start", null), 409)).isEqualTo("INTERVIEWERS_NOT_READY");

        JsonNode entered = json(expect(room.kim().post(room.session() + "/enter", null), 200));
        assertThat(attendee(entered, "PRACTICAL").path("entered").asBoolean()).isTrue();
        assertThat(attendee(entered, "PRACTICAL").path("online").asBoolean()).isTrue();
        assertThat(attendee(entered, "PRACTICAL").path("name").asString()).isEqualTo("김지민");
        assertThat(code(room.kim().post(room.session() + "/start", null), 409)).isEqualTo("INTERVIEWERS_NOT_READY");

        expect(room.people().post(room.session() + "/enter", null), 200);
        JsonNode started = json(expect(room.kim().post(room.session() + "/start", null), 200));
        assertThat(started.path("session").path("status").asString()).isEqualTo("IN_PROGRESS");

        JsonNode hr = json(expect(room.interview().hr().get(room.interview().stage() + "/interview/sessions"), 200));
        assertThat(hr.get(0).path("applicationId").asString()).isEqualTo(room.interview().applicationId().toString());
        assertThat(hr.get(0).path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(hr.get(0).path("attendees")).hasSize(2);
        // 면접관은 HR 진행 현황 경로를 열 수 없다
        expect(room.kim().get(room.interview().stage() + "/interview/sessions"), 403);
    }

    @Test
    @DisplayName("다른 면접관이 입장하면 열어 둔 면접관 화면과 HR 화면에 SSE로 바로 알린다")
    void changesArePushedOverSse() throws Exception {
        Room room = room();
        HttpResponse<Stream<String>> hrStream = room.interview().hr()
                .stream(room.interview().stage() + "/interview/events").get(10, TimeUnit.SECONDS);
        HttpResponse<Stream<String>> kimStream = room.kim().stream(room.session() + "/events")
                .get(10, TimeUnit.SECONDS);
        assertThat(kimStream.statusCode()).isEqualTo(200);
        assertThat(kimStream.headers().firstValue("Content-Type").orElse("")).startsWith("text/event-stream");
        Iterator<String> hrEvents = hrStream.body().iterator();
        Iterator<String> kimEvents = kimStream.body().iterator();
        // 면접관이 화면을 열면 접속 중으로 보이도록 HR 화면과 자기 화면에 알린다
        assertThat(nextEvent(hrEvents)).isEqualTo("changed");
        assertThat(nextEvent(kimEvents)).isEqualTo("changed");

        expect(room.people().post(room.session() + "/enter", null), 200);

        assertThat(nextEvent(kimEvents)).isEqualTo("changed");
        assertThat(nextEvent(hrEvents)).isEqualTo("changed");
        kimStream.body().close();
        hrStream.body().close();
    }

    private static String nextEvent(Iterator<String> lines) throws Exception {
        return CompletableFuture.supplyAsync(() -> {
            while (lines.hasNext()) {
                String line = lines.next();
                String name = line.startsWith("event:") ? line.substring("event:".length()).trim() : "";
                if (!name.isEmpty() && !name.equals("connected") && !name.equals("ping")) {
                    return name;
                }
            }
            return "";
        }).get(Duration.ofSeconds(10).toMillis(), TimeUnit.MILLISECONDS);
    }

    private record Room(Interview interview, TestApi kim, TestApi people) {

        String session() {
            return "/api/interviewer/sessions/" + interview.stageId() + "/" + interview.applicationId();
        }
    }

    /** 인사는 면접관 최인사, 실무는 면접관 김지민으로 배정한 면접. 담당이 빈 질문은 없다. */
    private Room room() throws Exception {
        Interview interview = interviewStage();
        TestApi kim = newInterviewer(interview.hr(), "김지민");
        TestApi people = newInterviewer(interview.hr(), "최인사");
        Map<String, Object> body = new HashMap<>();
        body.put("hrMemberId", people.memberId().toString());
        body.put("practicalMemberId", kim.memberId().toString());
        body.put("expectedVersion", null);
        expect(interview.hr().put(interview.candidate() + "/interview/session", body), 200);
        // 앞 전형 확정 때 AI가 미리 만드는 질문이 다 들어온 뒤에 시작한다 (만드는 중이면 시작할 수 없다)
        long deadline = System.currentTimeMillis() + 15_000;
        while (System.currentTimeMillis() < deadline && (json(expect(interview.hr().get(interview.candidate()
                + "/interview/preparing"), 200)).path("preparing").asBoolean() || json(expect(interview.hr()
                .get(interview.candidate() + "/interview"), 200)).path("questions").isEmpty())) {
            Thread.sleep(200);
        }
        return new Room(interview, kim, people);
    }

    private static JsonNode attendee(JsonNode attendance, String role) {
        for (JsonNode attendee : attendance.path("attendees")) {
            if (attendee.path("role").asString().equals(role)) {
                return attendee;
            }
        }
        throw new AssertionError("No attendee " + role + ": " + attendance);
    }

    private static String code(HttpResponse<String> response, int status) {
        return json(expect(response, status)).path("code").asString();
    }
}
