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
import com.hiremate.interview.domain.InterviewAttendance;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
import com.hiremate.interview.domain.InterviewSchedule;
import com.hiremate.interview.domain.InterviewScheduleRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
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
    private InterviewScheduleRepository schedules;

    @Autowired
    private InterviewSessionRepository sessions;

    @Autowired
    private InterviewAttendanceRepository attendance;

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Test
    @DisplayName("메일 발송 없이 결과 확정만으로 평일 아홉 칸을 배정하며 주말과 재시도를 처리한다")
    void assignsAfterConfirmationAndPreservesTimesOnRetry() throws Exception {
        Room room = room(11, false);
        List<UUID> passed = room.ids().subList(0, 10);
        guide(room, room.next(), friday());
        int before = mail.sent.size();
        confirm(room, passed);
        await(room, "READY");
        assertThat(mail.sent).hasSize(before);
        List<Instant> actual = times(room, passed);
        assertThat(actual.subList(0, 9)).containsExactlyElementsOf(List.of(9, 10, 11, 12, 13, 14, 15, 16, 17).stream()
                .map(hour -> friday().atTime(hour, 0).atZone(KOREA).toInstant()).toList());
        // 다음 면접 날짜가 없으면 같은 시간에 몰아넣지 않고 다음 평일(월요일)로 넘어간다
        assertThat(actual.get(9)).isEqualTo(friday().plusDays(3).atTime(9, 0).atZone(KOREA).toInstant());
        expect(room.hr().post(room.status() + "/retry", null), 200);
        await(room, "READY");
        assertThat(times(room, passed)).containsExactlyElementsOf(actual);
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        expect(room.hr().post(room.path() + "/notices/FAIL/send", null), 200);
        expect(room.hr().post(room.path() + "/finish", null), 200);
        String card = "/api/stages/" + room.next() + "/candidates/" + passed.get(9) + "/interview";
        assertThat(json(expect(room.hr().get(card), 200)).path("schedule").path("scheduledAt").asString())
                .isEqualTo(actual.get(9).toString());
        expect(room.hr().get("/api/stages/" + room.next() + "/candidates/" + room.ids().get(10) + "/interview"), 404);
    }

    @Test
    @DisplayName("날짜가 없을 때 기존 메일 발송은 유지하며 날짜를 저장하면 재시도 없이 배정한다")
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
        await(room, "READY");
        assertThat(mail.sent).hasSize(sent);
        assertThat(times(room, room.ids())).containsExactly(friday().atTime(9, 0).atZone(KOREA).toInstant());
    }

    @Test
    @DisplayName("날짜 변경은 자동 일정만 다시 배정하고 수동 시간·수동으로 비운 시간·기존 일정은 보존한다")
    void changedGuidePreservesManualAndLegacySchedules() throws Exception {
        Room room = room(4, false);
        guide(room, room.next(), friday());
        confirm(room, room.ids());
        await(room, "READY");
        Instant manual = friday().plusWeeks(1).atTime(9, 30).atZone(KOREA).toInstant();
        // 아직 시작하지 않은 다음 전형에 수동으로 고친 시간과 구분값 없는 기존 데이터가 있는 상황.
        InterviewSchedule moved = schedule(room, 0);
        moved.change(manual, "담당 면접관");
        schedules.saveAndFlush(moved);
        InterviewSchedule cleared = schedule(room, 1);
        cleared.change(null, "");
        schedules.saveAndFlush(cleared);
        InterviewSchedule legacy = new InterviewSchedule(room.next(), room.ids().get(2), room.hr().companyId());
        Instant legacyTime = schedule(room, 2).getScheduledAt();
        legacy.change(legacyTime, "기존 담당자");
        schedules.saveAndFlush(legacy);
        InterviewSchedule metadataOnly = schedule(room, 3);
        metadataOnly.change(metadataOnly.getScheduledAt(), "이름만 변경");
        schedules.saveAndFlush(metadataOnly);
        guide(room, room.next(), friday().plusWeeks(1));
        await(room, "READY");
        assertThat(schedule(room, 0).getScheduledAt()).isEqualTo(manual);
        assertThat(schedule(room, 0).getInterviewers()).isEqualTo("담당 면접관");
        assertThat(schedule(room, 1).getScheduledAt()).isNull();
        assertThat(schedule(room, 2).getScheduledAt()).isEqualTo(legacyTime);
        assertThat(schedule(room, 3).getScheduledAt())
                .isEqualTo(friday().plusWeeks(1).atTime(11, 0).atZone(KOREA).toInstant());
        assertThat(schedule(room, 3).isAutomaticallyScheduled()).isTrue();
        assertThat(schedule(room, 3).getInterviewers()).isEqualTo("이름만 변경");
        List<Instant> assigned = times(room, room.ids());
        expect(room.hr().post(room.status() + "/retry", null), 200);
        await(room, "READY");
        assertThat(times(room, room.ids())).containsExactlyElementsOf(assigned);
    }

    @Test
    @DisplayName("시작·종료된 면접은 보존하고 옮긴 예정 면접의 준비 완료만 거둔다")
    void preservesStartedSessionsAndClearsReadinessWhenMoved() throws Exception {
        Room room = room(3, false);
        guide(room, room.next(), friday());
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> assigned = times(room, room.ids());
        UUID practical = newInterviewer(room.hr(), "실무 면접관").memberId();
        for (int i = 0; i < room.ids().size(); i++) {
            InterviewSession session = new InterviewSession(room.hr().companyId(), room.next(), room.ids().get(i),
                    room.hr().memberId(), practical);
            if (i < 2) {
                session.start(Instant.now());
            }
            if (i == 1) {
                session.end(Instant.now());
            }
            sessions.saveAndFlush(session);
        }
        UUID waiting = room.ids().get(2);
        attendance.saveAndFlush(new InterviewAttendance(room.next(), waiting, practical, room.hr().companyId()));
        guide(room, room.next(), friday().plusWeeks(1));
        await(room, "READY");
        assertThat(schedule(room, 0).getScheduledAt()).isEqualTo(assigned.get(0));
        assertThat(schedule(room, 1).getScheduledAt()).isEqualTo(assigned.get(1));
        assertThat(schedule(room, 2).getScheduledAt())
                .isEqualTo(friday().plusWeeks(1).atTime(9, 0).atZone(KOREA).toInstant());
        assertThat(attendance.existsByStageIdAndApplicationId(room.next(), waiting)).isFalse();
        assertThat(sessions.findById(new InterviewSession.Key(room.next(), room.ids().get(0))).orElseThrow()
                .getStatus()).isEqualTo(InterviewSessionStatus.IN_PROGRESS);
    }

    @Test
    @DisplayName("재배정 실패 후 메일을 보냈으면 날짜를 고쳐도 이전 자동 일정을 보존한다")
    void cancelsFailedReassignmentWhenGuideIsSavedAfterMail() throws Exception {
        Room room = room(1, true);
        guide(room, room.next(), friday());
        guide(room, room.last(), friday().plusDays(3));
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> assigned = times(room, room.ids());
        guide(room, room.next(), friday().plusDays(1));
        await(room, "FAILED");
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        guide(room, room.next(), friday().minusDays(1));
        await(room, "READY");
        assertThat(times(room, room.ids())).containsExactlyElementsOf(assigned);
    }

    @Test
    @DisplayName("합격 메일을 보낸 뒤에는 날짜를 바꿔도 이미 배정한 시간을 자동으로 옮기지 않는다")
    void doesNotReassignAfterPassMail() throws Exception {
        Room room = room(2, false);
        guide(room, room.next(), friday());
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> assigned = times(room, room.ids());
        expect(room.hr().post(room.path() + "/notices/prepare", null), 200);
        expect(room.hr().post(room.path() + "/notices/PASS/send", null), 200);
        guide(room, room.next(), friday().plusWeeks(1));
        await(room, "READY");
        assertThat(times(room, room.ids())).containsExactlyElementsOf(assigned);
    }

    @Test
    @DisplayName("재배정할 평일이 없으면 기존 자동 일정을 보존하고 날짜를 고친 뒤 다시 배정한다")
    void failedReassignmentKeepsExistingTimes() throws Exception {
        Room room = room(2, true);
        guide(room, room.next(), friday());
        guide(room, room.last(), friday().plusDays(3));
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> assigned = times(room, room.ids());
        guide(room, room.next(), friday().plusDays(1));
        await(room, "FAILED");
        assertThat(times(room, room.ids())).containsExactlyElementsOf(assigned);
        guide(room, room.next(), friday().minusDays(1));
        await(room, "READY");
        assertThat(times(room, room.ids())).containsExactly(
                friday().minusDays(1).atTime(9, 0).atZone(KOREA).toInstant(),
                friday().minusDays(1).atTime(10, 0).atZone(KOREA).toInstant());
    }

    private InterviewSchedule schedule(Room room, int index) {
        return schedules.findById(new InterviewSchedule.Key(room.next(), room.ids().get(index))).orElseThrow();
    }

    @Test
    @DisplayName("다음 면접 전까지 칸이 충분하면 한 칸에 한 명씩 앞에서부터 배정한다")
    void assignsOnePerSlotWhenSlotsAreEnough() throws Exception {
        Room room = room(11, true);
        guide(room, room.next(), friday());
        // 금요일 아홉 칸과 월요일 아홉 칸을 쓸 수 있다
        guide(room, room.last(), friday().plusDays(4));
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> expected = new ArrayList<>();
        for (int hour : List.of(9, 10, 11, 12, 13, 14, 15, 16, 17)) {
            expected.add(friday().atTime(hour, 0).atZone(KOREA).toInstant());
        }
        expected.add(friday().plusDays(3).atTime(9, 0).atZone(KOREA).toInstant());
        expected.add(friday().plusDays(3).atTime(10, 0).atZone(KOREA).toInstant());
        assertThat(times(room, room.ids())).containsExactlyElementsOf(expected);
    }

    @Test
    @DisplayName("다음 면접 전까지 칸이 모자라면 모든 칸에 고르게 나눠 같은 시간에 배정한다")
    void sharesSlotsWhenApplicantsExceedSlots() throws Exception {
        Room room = room(20, true);
        guide(room, room.next(), friday());
        // 다음 면접이 월요일이라 금요일 아홉 칸뿐이다. 20명은 앞 두 칸에 3명, 나머지 일곱 칸에 2명씩이다
        guide(room, room.last(), friday().plusDays(3));
        confirm(room, room.ids());
        await(room, "READY");
        List<Instant> expected = new ArrayList<>();
        for (int hour : List.of(9, 10, 11, 12, 13, 14, 15, 16, 17)) {
            int people = hour <= 10 ? 3 : 2;
            for (int person = 0; person < people; person++) {
                expected.add(friday().atTime(hour, 0).atZone(KOREA).toInstant());
            }
        }
        assertThat(times(room, room.ids())).containsExactlyElementsOf(expected);
    }

    @Test
    @DisplayName("배정할 칸이 하나도 없으면 일정을 만들지 않되 메일 발송은 유지하며 날짜 조정 뒤 재시도한다")
    void noSlotsLeavesSchedulesEmptyWithoutChangingMailFlow() throws Exception {
        Room room = room(6, true);
        // 토요일부터 월요일 전까지라 평일 칸이 없다
        guide(room, room.next(), friday().plusDays(1));
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
