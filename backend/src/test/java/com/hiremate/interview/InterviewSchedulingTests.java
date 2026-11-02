package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.TestMailConfiguration;
import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

/** 공고 날짜를 읽어 결과 확정 뒤 배정하며, 기존 메일 발송은 가로막지 않는다. */
class InterviewSchedulingTests extends IntegrationTest {

    private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

    @Autowired
    private ApplicationService applications;

    @Autowired
    private InterviewService interviews;

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Test
    @DisplayName("메일 발송 없이 결과 확정만으로 평일 다섯 칸을 배정하며 주말과 재시도를 처리한다")
    void assignsAfterConfirmationAndPreservesTimesOnRetry() throws Exception {
        Room room = room(7, false);
        List<UUID> passed = room.ids().subList(0, 6);
        guide(room, room.next(), friday());
        int before = mail.sent.size();
        confirm(room, passed);
        await(room, "READY");
        assertThat(mail.sent).hasSize(before);
        List<Instant> actual = times(room, passed);
        assertThat(actual.subList(0, 5)).containsExactlyElementsOf(List.of(9, 10, 14, 15, 16).stream()
                .map(hour -> friday().atTime(hour, 0).atZone(KOREA).toInstant()).toList());
        assertThat(actual.get(5)).isEqualTo(friday().plusDays(3).atTime(9, 0).atZone(KOREA).toInstant());
        expect(room.hr().post(room.status() + "/retry", null), 200);
        await(room, "READY");
        assertThat(times(room, passed)).containsExactlyElementsOf(actual);
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        expect(room.hr().post(room.path() + "/notices/FAIL/send", null), 200);
        expect(room.hr().post(room.path() + "/finish", null), 200);
        String card = "/api/stages/" + room.next() + "/candidates/" + passed.get(5) + "/interview";
        assertThat(json(expect(room.hr().get(card), 200)).path("schedule").path("scheduledAt").asString())
                .isEqualTo(actual.get(5).toString());
        expect(room.hr().get("/api/stages/" + room.next() + "/candidates/" + room.ids().get(6) + "/interview"), 404);
    }

    @Test
    @DisplayName("공고 날짜가 없으면 상태만 알리고 기존 메일 발송은 유지하며 날짜 설정 후 HR만 재시도한다")
    void missingDateDoesNotBlockMailAndCanBeRetried() throws Exception {
        Room room = room(1, false);
        confirm(room, room.ids());
        await(room, "DATE_REQUIRED");
        expect(newHr().get(room.status()), 404);
        expect(newInterviewer(room.hr(), "면접관").post(room.status() + "/retry", null), 403);
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        int sent = mail.sent.size();
        guide(room, room.next(), friday());
        expect(room.hr().post(room.status() + "/retry", null), 200);
        await(room, "READY");
        assertThat(mail.sent).hasSize(sent);
        assertThat(times(room, room.ids())).containsExactly(friday().atTime(9, 0).atZone(KOREA).toInstant());
    }

    @Test
    @DisplayName("배정 가능한 날이 부족하면 부분 배정은 롤백하되 메일 발송은 유지하며 날짜 조정 뒤 재시도한다")
    void overflowRollsBackSchedulesWithoutChangingMailFlow() throws Exception {
        Room room = room(6, true);
        guide(room, room.next(), friday());
        guide(room, room.last(), friday().plusDays(3));
        int before = mail.sent.size();
        confirm(room, room.ids());
        JsonNode failed = await(room, "FAILED");
        assertThat(failed.path("errorCode").asString()).isEqualTo("INTERVIEW_SCHEDULE_CAPACITY");
        assertThat(mail.sent).hasSize(before);
        assertThat(interviews.preparationView(room.hr().companyId(), room.next(), room.ids().getFirst()).schedule())
                .isNull();
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        int sent = mail.sent.size();
        guide(room, room.last(), friday().plusWeeks(2));
        expect(room.hr().post(room.status() + "/retry", null), 200);
        await(room, "READY");
        assertThat(times(room, room.ids())).hasSize(6).doesNotHaveDuplicates();
        assertThat(mail.sent).hasSize(sent);
    }

    private Room room(int count, boolean finalInterview) throws Exception {
        TestApi hr = newHr();
        String plan = finalInterview ? "전형은 서류, 1차 면접, 최종 면접 순으로 해줘"
                : "전형은 서류, 1차 면접 순으로 해줘";
        TestFixtures.Posting posting = TestFixtures.publish(hr, false, plan);
        for (int i = 0; i < count; i++) {
            expect(anonymous().multipart(posting.applyPath(), TestFixtures.form(UUID.randomUUID() + "@example.com",
                    false)), 201);
        }
        UUID recruitment = UUID.fromString(posting.recruitmentId());
        List<UUID> ids = applications.applicants(hr.companyId(), recruitment).stream()
                .sorted(Comparator.comparingInt(ApplicantInfo::applicationNo))
                .map(ApplicantInfo::applicationId).toList();
        JsonNode stages = json(expect(hr.post("/api/recruitments/" + recruitment + "/posting/close", null), 200))
                .path("stages");
        return new Room(hr, stages.get(0).path("id").asString(),
                UUID.fromString(stages.get(1).path("id").asString()),
                finalInterview ? UUID.fromString(stages.get(2).path("id").asString()) : null, ids);
    }

    private static void confirm(Room room, List<UUID> passed) throws Exception {
        expect(room.hr().post(room.path() + "/decisions", Map.of("applicationIds", passed, "decision", "PASS")), 204);
        expect(room.hr().post(room.path() + "/confirm", null), 200);
    }

    private static void guide(Room room, UUID stageId, LocalDate date) throws Exception {
        expect(room.hr().put("/api/stages/" + stageId + "/guide", Map.of("schedule", date.toString(),
                "place", "", "preparation", "", "note", "")), 200);
    }

    private List<Instant> times(Room room, List<UUID> ids) {
        List<Instant> times = new ArrayList<>();
        for (UUID id : ids) {
            times.add(interviews.preparationView(room.hr().companyId(), room.next(), id).schedule().scheduledAt());
        }
        return times;
    }

    private static JsonNode await(Room room, String expected) throws Exception {
        Instant deadline = Instant.now().plusSeconds(20);
        JsonNode state;
        do {
            state = json(expect(room.hr().get(room.status()), 200));
            if (state.path("status").asString().equals(expected)) {
                return state;
            }
            Thread.sleep(50);
        } while (Instant.now().isBefore(deadline));
        throw new AssertionError("Expected " + expected + ": " + state);
    }

    private static LocalDate friday() {
        return LocalDate.now(KOREA).plusWeeks(2).with(TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY));
    }

    private record Room(TestApi hr, String document, UUID next, UUID last, List<UUID> ids) {

        String path() {
            return "/api/stages/" + document;
        }

        String status() {
            return path() + "/interview-scheduling";
        }
    }
}
