package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

/**
 * 면접관 준비 완료와 실시간 알림. 배정된 면접관이 모두 [준비 완료]를 누르고 접속 중이면 면접이 바로 시작된다.
 * 준비 · 시작 같은 변화는 SSE로 다른 면접관 화면과 HR 화면에 바로 알리고, 시작한 면접은 HR 알림에 보인다.
 */
class InterviewAttendanceTests extends IntegrationTest {

    @Autowired
    private InterviewService interviews;

    @Autowired
    private InterviewAttendanceRepository attendance;

    @Test
    @DisplayName("두 면접관이 모두 준비 완료하면 바로 시작하고, 준비 현황과 시작 알림은 HR에게 보인다")
    void startsWhenEveryInterviewerIsReady() throws Exception {
        Room room = room();

        JsonNode before = json(expect(room.kim().get(room.session() + "/attendance"), 200));
        assertThat(before.path("stageActive").asBoolean()).isTrue();
        assertThat(before.path("attendees")).hasSize(2);
        assertThat(before.path("attendees").get(0).path("ready").asBoolean()).isFalse();

        JsonNode ready = json(expect(room.kim().post(room.session() + "/ready", null), 200));
        assertThat(attendee(ready, "PRACTICAL").path("ready").asBoolean()).isTrue();
        assertThat(attendee(ready, "PRACTICAL").path("online").asBoolean()).isTrue();
        assertThat(attendee(ready, "PRACTICAL").path("name").asString()).isEqualTo("김지민");
        assertThat(attendee(ready, "HR").path("ready").asBoolean()).isFalse();
        assertThat(status(room)).isEqualTo("SCHEDULED");

        // 상대가 준비하기 전에는 준비 완료를 거둘 수 있다
        JsonNode cancelled = json(expect(room.kim().delete(room.session() + "/ready"), 200));
        assertThat(attendee(cancelled, "PRACTICAL").path("ready").asBoolean()).isFalse();
        expect(room.people().post(room.session() + "/ready", null), 200);
        assertThat(status(room)).isEqualTo("SCHEDULED");

        expect(room.kim().post(room.session() + "/ready", null), 200);
        assertThat(status(room)).isEqualTo("IN_PROGRESS");
        // 시작한 뒤의 준비 취소는 면접을 되돌리지 않는다
        expect(room.kim().delete(room.session() + "/ready"), 200);
        assertThat(status(room)).isEqualTo("IN_PROGRESS");

        JsonNode hr = json(expect(room.interview().hr().get(room.interview().stage() + "/interview/sessions"), 200));
        assertThat(hr.get(0).path("applicationId").asString()).isEqualTo(room.interview().applicationId().toString());
        assertThat(hr.get(0).path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(hr.get(0).path("attendees")).hasSize(2);
        assertThat(hr.get(0).path("attendees").get(0).path("ready").asBoolean()).isTrue();

        JsonNode started = json(expect(room.interview().hr().get("/api/companies/current/interviews/started"), 200));
        assertThat(started).hasSize(1);
        assertThat(started.get(0).path("applicationId").asString())
                .isEqualTo(room.interview().applicationId().toString());
        assertThat(started.get(0).path("stageId").asString()).isEqualTo(room.interview().stageId().toString());
        assertThat(started.get(0).path("applicantName").asString()).isNotBlank();
        assertThat(started.get(0).path("stageName").asString()).isNotBlank();
        assertThat(started.get(0).path("startedAt").asString()).isNotBlank();
        // 면접관은 HR 진행 현황과 HR 알림을 열 수 없다
        expect(room.kim().get(room.interview().stage() + "/interview/sessions"), 403);
        expect(room.kim().get("/api/companies/current/interviews/started"), 403);
    }

    @Test
    @DisplayName("시작 전에 화면을 떠난 면접관의 준비 완료는 거두고, 시작한 면접의 기록은 남긴다")
    void leavingBeforeStartReleasesReady() throws Exception {
        Room room = room();
        expect(room.kim().post(room.session() + "/ready", null), 200);

        attendance.release(room.interview().stageId(), room.interview().applicationId(), room.kim().memberId(),
                InterviewSessionStatus.SCHEDULED);
        JsonNode released = json(expect(room.people().get(room.session() + "/attendance"), 200));
        assertThat(attendee(released, "PRACTICAL").path("ready").asBoolean()).isFalse();
        expect(room.people().post(room.session() + "/ready", null), 200);
        assertThat(status(room)).isEqualTo("SCHEDULED");

        expect(room.kim().post(room.session() + "/ready", null), 200);
        assertThat(status(room)).isEqualTo("IN_PROGRESS");
        attendance.release(room.interview().stageId(), room.interview().applicationId(), room.kim().memberId(),
                InterviewSessionStatus.SCHEDULED);
        JsonNode kept = json(expect(room.people().get(room.session() + "/attendance"), 200));
        assertThat(attendee(kept, "PRACTICAL").path("ready").asBoolean()).isTrue();
    }

    @Test
    @DisplayName("다른 면접관이 준비 완료하면 열어 둔 면접관 화면과 HR 화면에 SSE로 바로 알린다")
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

        expect(room.people().post(room.session() + "/ready", null), 200);

        assertThat(nextEvent(kimEvents)).isEqualTo("changed");
        assertThat(nextEvent(hrEvents)).isEqualTo("changed");
        kimStream.body().close();
        hrStream.body().close();
    }

    @Test
    @DisplayName("HR이 질문 담당을 채우면 대기 중인 면접관 화면에 바로 알린다")
    void questionOwnerChangesReachWaitingRoom() throws Exception {
        Room room = room();
        try (Stream<String> stream = room.kim().stream(room.session() + "/events")
                .get(10, TimeUnit.SECONDS).body()) {
            Iterator<String> events = stream.iterator();
            assertThat(nextEvent(events)).isEqualTo("changed");
            JsonNode workspace = json(expect(room.kim().get(room.session()), 200));
            String questionId = workspace.path("questions").get(0).path("question").path("questionId").asString();

            expect(room.interview().hr().put(room.interview().stage() + "/interview/questions/" + questionId
                    + "/role", Map.of("interviewerRole", "HR")), 200);

            assertThat(nextEvent(events)).isEqualTo("changed");
        }
    }

    @Test
    @DisplayName("새 AI 질문을 열린 면접관 화면에 바로 알린다")
    void generatedQuestionsReachRoom() throws Exception {
        Room room = room();
        try (Stream<String> stream = room.kim().stream(room.session() + "/events")
                .get(10, TimeUnit.SECONDS).body()) {
            Iterator<String> events = stream.iterator();
            assertThat(nextEvent(events)).isEqualTo("changed");

            interviews.addGeneratedQuestions(room.interview().hr().companyId(), room.interview().stageId(),
                    room.interview().applicationId(),
                    List.of(new InterviewQuestionDraft("장애를 복구할 때 본인이 맡은 일을 설명해 주세요.", null,
                            InterviewerRole.PRACTICAL)));
            assertThat(nextEvent(events)).isEqualTo("changed");
        }
    }

    @Test
    @DisplayName("질문 생성 대기가 끝나면 열린 면접관 화면에 바로 알린다")
    void preparationCompletionReachesRoom() throws Exception {
        Room room = room();
        interviews.startPreparing(room.interview().hr().companyId(), room.interview().stageId(),
                room.interview().applicationId());
        try (Stream<String> stream = room.kim().stream(room.session() + "/events")
                .get(10, TimeUnit.SECONDS).body()) {
            Iterator<String> events = stream.iterator();
            assertThat(nextEvent(events)).isEqualTo("changed");

            interviews.finishPreparing(room.interview().hr().companyId(), room.interview().stageId(),
                    room.interview().applicationId());

            assertThat(nextEvent(events)).isEqualTo("changed");
        }
    }

    @Test
    @DisplayName("HR이 결과를 확정하면 면접관 화면에 알리고 의견을 읽기 전용으로 바꾼다")
    void stageConfirmationReachesRoom() throws Exception {
        Room room = room();
        try (Stream<String> stream = room.kim().stream(room.session() + "/events")
                .get(10, TimeUnit.SECONDS).body()) {
            Iterator<String> events = stream.iterator();
            assertThat(nextEvent(events)).isEqualTo("changed");

            expect(room.interview().hr().post(room.interview().stage() + "/confirm", null), 200);

            assertThat(nextEvent(events)).isEqualTo("changed");
            JsonNode attendance = json(expect(room.kim().get(room.session() + "/attendance"), 200));
            assertThat(attendance.path("stageActive").asBoolean()).isFalse();
        }
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
        expect(interview.hr().put(interview.stage() + "/interview/assignment", body), 200);
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

    private static String status(Room room) throws Exception {
        return json(expect(room.kim().get(room.session()), 200)).path("session").path("status").asString();
    }
}
