package com.hiremate.auth;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationService;
import com.hiremate.auth.domain.Member;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageType;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.crypto.password.PasswordEncoder;
import tools.jackson.databind.JsonNode;

class InterviewerSessionTests extends IntegrationTest {

    @Autowired
    private MemberRepository members;

    @Autowired
    private PasswordEncoder passwords;

    @Autowired
    private ApplicationService applications;

    @Autowired
    private InterviewService interviews;

    @Autowired
    private RecruitService recruits;

    @Test
    @DisplayName("배정·질문 우선 정렬·개인 메모·담당별 입력 제한과 종료 후 잠금을 HTTP로 검증한다")
    void assignedInterviewersHaveScopedPermissions() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        JsonNode listed = json(expect(f.practical().api().get("/api/interviewer/sessions"), 200));
        assertThat(listed.path("items").size()).isEqualTo(1);
        assertThat(listed.path("items").get(0).path("myRole").asString()).isEqualTo("PRACTICAL");
        // 면접관 모드는 면접관 계정만 쓴다. HR 계정은 배정되지 않고 면접관 경로도 열 수 없다
        expect(newHr().get(f.workspace()), 403);
        expect(f.hr().get(f.workspace()), 403);
        expect(f.unassigned().api().get(f.workspace()), 403);
        expect(f.practical().api().get("/api/stages/" + f.stageId()), 403);
        expect(f.practical().api().put(f.admin(), assignment(f)), 403);

        JsonNode scheduled = json(expect(f.people().api().get(f.workspace()), 200));
        assertThat(scheduled.path("session").path("status").asString()).isEqualTo("SCHEDULED");
        assertThat(scheduled.path("questions").get(0).path("canAnswer").asBoolean()).isFalse();
        expect(f.people().api().put(f.workspace() + "/memo",
                Map.of("text", "시작 전 메모", "expectedVersion", 0)), 409);
        expect(f.unassigned().api().put(f.workspace() + "/memo",
                Map.of("text", "미배정 메모", "expectedVersion", 0)), 403);
        readyBoth(f);
        JsonNode started = json(expect(f.people().api().get(f.workspace()), 200));
        assertThat(started.path("session").path("status").asString()).isEqualTo("IN_PROGRESS");
        JsonNode practical = json(expect(f.practical().api().get(f.workspace()), 200));
        assertThat(practical.path("questions").get(0).path("question").path("interviewerRole").asString())
                .isEqualTo("PRACTICAL");
        assertThat(practical.path("questions").get(0).path("canAnswer").asBoolean()).isTrue();

        JsonNode hrQuestion = question(started, "HR");
        JsonNode jobQuestion = question(started, "PRACTICAL");
        String jobId = jobQuestion.path("questionId").asString();
        String hrId = hrQuestion.path("questionId").asString();
        expect(f.practical().api().put(answerPath(f, hrId), answer(hrQuestion, "다른 담당")), 403);
        expect(f.hr().put(f.legacy() + "/interview/questions/" + jobId + "/answer", answer(jobQuestion, "우회")), 403);
        expect(f.unassigned().api().put(f.legacy() + "/interview/questions/" + hrId + "/answer",
                answer(hrQuestion, "미배정 우회")), 403);
        JsonNode saved = json(expect(f.practical().api().put(answerPath(f, jobId),
                answer(jobQuestion, "직접 개발한 기능입니다.")), 200));
        long version = saved.path("questions").valueStream()
                .filter(item -> item.path("questionId").asString().equals(jobId))
                .findFirst().orElseThrow().path("version").asLong();
        assertThat(version).isGreaterThan(jobQuestion.path("version").asLong());
        expect(f.practical().api().put(answerPath(f, jobId), answer(jobQuestion, "오래된 자동 저장")), 409);
        expect(f.practical().api().post(f.workspace() + "/questions",
                Map.of("text", "다른 역할 질문", "interviewerRole", "HR")), 403);
        expect(f.practical().api().post(f.questionRoot() + hrId + "/follow-ups/suggestions",
                Map.of("avoid", List.of())), 403);
        expect(f.practical().api().delete(f.questionRoot() + jobId), 409);
        expect(f.hr().put(f.legacy() + "/interview/questions/" + jobId + "/role",
                Map.of("interviewerRole", "HR")), 409);
        expect(f.hr().post(f.legacy() + "/candidates/" + f.applicationId()
                + "/interview/questions/regenerate", null), 409);

        JsonNode current = json(expect(f.people().api().get(f.workspace()), 200));
        JsonNode noted = json(expect(f.people().api().put(f.workspace() + "/memo",
                Map.of("text", "PRIVATE-HR-NOTE", "expectedVersion",
                        current.path("personalMemoVersion").asLong())), 200));
        assertThat(noted.path("personalMemo").asString()).isEqualTo("PRIVATE-HR-NOTE");
        String other = expect(f.practical().api().get(f.workspace()), 200).body();
        assertThat(other).doesNotContain("PRIVATE-HR-NOTE", "hrMemo", "practicalMemo");
        // 먼저 [면접 종료]를 누른 면접관은 기록이 잠기고, 상대 면접관은 계속 진행한다
        JsonNode mine = json(expect(f.practical().api().post(f.workspace() + "/end", null), 200));
        assertThat(mine.path("session").path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(mine.path("questions").valueStream().allMatch(row -> !row.path("canAnswer").asBoolean()))
                .isTrue();
        assertThat(code(f.practical().api().put(answerPath(f, jobId),
                Map.of("answer", "늦게 도착한 저장", "analyze", false, "expectedVersion", version)), 409))
                .isEqualTo("INTERVIEWER_ENDED");
        assertThat(code(f.practical().api().put(f.workspace() + "/memo", Map.of("text", "종료 후 실무 메모",
                "expectedVersion", mine.path("personalMemoVersion").asLong())), 409)).isEqualTo("INTERVIEWER_ENDED");
        JsonNode attendees = json(expect(f.people().api().get(f.workspace() + "/attendance"), 200))
                .path("attendees");
        assertThat(attendees.valueStream().map(person -> person.path("role").asString() + ":"
                + person.path("ended").asBoolean())).containsExactly("HR:false", "PRACTICAL:true");
        noted = json(expect(f.people().api().put(f.workspace() + "/memo", Map.of("text", "상대가 끝낸 뒤 메모",
                "expectedVersion", noted.path("personalMemoVersion").asLong())), 200));

        // 두 면접관이 모두 마치면 면접이 끝난다
        JsonNode ended = json(expect(f.people().api().post(f.workspace() + "/end", null), 200));
        assertThat(ended.path("session").path("status").asString()).isEqualTo("ENDED");
        expect(f.people().api().put(f.workspace() + "/memo", Map.of("text", "종료 후 메모",
                "expectedVersion", noted.path("personalMemoVersion").asLong())), 409);
        assertThat(ended.path("questions").valueStream().allMatch(row -> !row.path("canAnswer").asBoolean()))
                .isTrue();
        expect(f.hr().put(f.admin(), assignment(f)), 409);
        assertThatThrownBy(() -> interviews.addGeneratedQuestions(f.hr().companyId(),
                UUID.fromString(f.stageId()), f.applicationId(),
                List.of(new InterviewQuestionDraft("종료 후 늦게 온 AI 질문", null, InterviewerRole.PRACTICAL))))
                .isInstanceOf(com.hiremate.global.ApiException.class);
    }

    @Test
    @DisplayName("동일인·타기업 배정을 거절하고 미지정 질문이 있으면 시작할 수 없다")
    void assignmentAndQuestionOwnersAreValidated() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), Map.of("hrMemberId", f.people().id(),
                "practicalMemberId", f.people().id())), 400);
        expect(f.hr().put(f.admin(), Map.of("hrMemberId", f.people().id(),
                "practicalMemberId", newHr().memberId())), 400);
        // HR 계정은 면접관으로 배정하지 않는다
        assertThat(json(expect(f.hr().put(f.admin(), Map.of("hrMemberId", f.hr().memberId(),
                "practicalMemberId", f.practical().id())), 400)).path("code").asString())
                .isEqualTo("INVALID_INTERVIEWER");
        JsonNode unowned = json(expect(f.hr().post(f.legacy() + "/candidates/" + f.applicationId()
                + "/interview/questions", Map.of("text", "직접 추가한 확인 질문")), 200));
        String questionId = unowned.path("questions").valueStream()
                .filter(item -> item.path("text").asString().equals("직접 추가한 확인 질문"))
                .findFirst().orElseThrow().path("questionId").asString();
        JsonNode assigned = json(expect(f.hr().put(f.admin(), assignment(f)), 200));
        expect(f.hr().put(f.admin(), assignment(f)), 409);
        schedule(f, f.applicationId(), SLOT);
        // 담당이 없는 질문이 있으면 시작할 수 없으므로 준비 완료도 받지 않는다
        assertThat(json(expect(f.practical().api().post(f.workspace() + "/ready", null), 409)).path("code")
                .asString()).isEqualTo("QUESTION_OWNER_REQUIRED");
        expect(f.hr().put(f.legacy() + "/interview/questions/" + questionId + "/role",
                Map.of("interviewerRole", "PRACTICAL")), 200);
        readyBoth(f);
        assertThat(json(expect(f.people().api().get(f.workspace()), 200)).path("session").path("status")
                .asString()).isEqualTo("IN_PROGRESS");
        assertThat(assigned.path("hrMemberId").asString()).isEqualTo(f.people().id().toString());
        expect(f.hr().put(f.legacy() + "/interview/assignment",
                Map.of("hrMemberId", f.practical().id(), "practicalMemberId", f.people().id(),
                        "expectedVersion", assigned.path("version").asLong())), 409);
    }

    @Test
    @DisplayName("동일 버전의 동시 자동 저장은 하나만 성공하고 나머지는 충돌을 반환한다")
    void concurrentAutosavesCannotOverwriteEachOther() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        readyBoth(f);
        JsonNode started = json(expect(f.practical().api().get(f.workspace()), 200));
        JsonNode question = question(started, "PRACTICAL");
        String path = answerPath(f, question.path("questionId").asString());
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> one = executor.submit(() ->
                    f.practical().api().put(path, answer(question, "첫 번째 초안")).statusCode());
            Future<Integer> two = executor.submit(() ->
                    f.practical().api().put(path, answer(question, "두 번째 초안")).statusCode());
            assertThat(List.of(one.get(), two.get())).containsExactlyInAnyOrder(200, 409);
        }
    }

    @Test
    @DisplayName("진행 중인 면접은 전형 확정을 막고 종료 후 확정과 종료 재시도는 가능하다")
    void stageConfirmationRequiresEndedInterviews() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        readyBoth(f);
        JsonNode rejected = json(expect(f.hr().post(f.legacy() + "/confirm", null), 409));
        assertThat(rejected.path("code").asString()).isEqualTo("INTERVIEW_IN_PROGRESS");
        expect(f.people().api().post(f.workspace() + "/end", null), 200);
        // 한 면접관만 마쳤으면 아직 진행 중이다
        assertThat(code(f.hr().post(f.legacy() + "/confirm", null), 409)).isEqualTo("INTERVIEW_IN_PROGRESS");
        expect(f.practical().api().post(f.workspace() + "/end", null), 200);
        expect(f.hr().post(f.legacy() + "/confirm", null), 200);
        JsonNode ended = json(expect(f.people().api().post(f.workspace() + "/end", null), 200));
        assertThat(ended.path("session").path("status").asString()).isEqualTo("ENDED");
    }

    @Test
    @DisplayName("기존 미지정 질문의 답변을 보존하며 첫 담당을 지정하고 면접을 시작한다")
    void legacyAnswerCanReceiveItsFirstOwner() throws Exception {
        Fixture f = fixture();
        String card = f.legacy() + "/candidates/" + f.applicationId() + "/interview/questions";
        JsonNode added = json(expect(f.hr().post(card, Map.of("text", "기존 미지정 질문")), 200));
        String id = added.path("questions").valueStream()
                .filter(item -> item.path("text").asString().equals("기존 미지정 질문"))
                .findFirst().orElseThrow().path("questionId").asString();
        String root = f.legacy() + "/interview/questions/" + id;
        expect(f.hr().put(root + "/answer", Map.of("answer", "보존할 답변", "analyze", false)), 200);
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        expect(f.hr().delete(root), 409);
        JsonNode assigned = json(expect(f.hr().put(root + "/role", Map.of("interviewerRole", "PRACTICAL")), 200));
        assertThat(assigned.path("questions").valueStream()
                .filter(item -> item.path("questionId").asString().equals(id))
                .findFirst().orElseThrow().path("answer").asString()).isEqualTo("보존할 답변");
        expect(f.hr().post(card, Map.of("text", "배정 후 직접 질문", "interviewerRole", "HR")), 200);
        readyBoth(f);
        expect(f.hr().put(root + "/role", Map.of("interviewerRole", "HR")), 409);
    }

    @Test
    @DisplayName("면접 시작과 전형 확정이 동시에 도착하면 한 작업만 성공한다")
    void concurrentStartAndConfirmationCannotBothSucceed() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        schedule(f, f.applicationId(), SLOT);
        expect(f.practical().api().post(f.workspace() + "/ready", null), 200);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            // 두 번째 준비 완료가 면접을 시작한다
            Future<Integer> start = executor.submit(() ->
                    f.people().api().post(f.workspace() + "/ready", null).statusCode());
            Future<Integer> confirm = executor.submit(() -> f.hr().post(f.legacy() + "/confirm", null).statusCode());
            assertThat(List.of(start.get(), confirm.get())).containsExactlyInAnyOrder(200, 409);
        }
    }

    @Test
    @DisplayName("최초 배정이 동시에 도착해도 한 요청만 성공하고 나머지는 충돌이다")
    void concurrentFirstAssignmentsReturnConflict() throws Exception {
        Fixture f = fixture();
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> one = executor.submit(() -> f.hr().put(f.admin(), assignment(f)).statusCode());
            Future<Integer> two = executor.submit(() -> f.hr().put(f.admin(), assignment(f)).statusCode());
            assertThat(List.of(one.get(), two.get())).containsExactlyInAnyOrder(200, 409);
        }
    }

    @Test
    @DisplayName("전형에서 한 번 배정하면 지원자 전원에게 적용되고 지원자별 배정은 허용하지 않는다")
    void stageAssignmentAppliesToEveryCandidate() throws Exception {
        Fixture f = fixture(2, false);
        JsonNode assigned = json(expect(f.hr().put(f.legacy() + "/interview/assignment", assignment(f)), 200));
        assertThat(assigned.path("stageId").asString()).isEqualTo(f.stageId());
        assertThat(assigned.path("locked").asBoolean()).isFalse();
        JsonNode listed = json(expect(f.practical().api().get("/api/interviewer/sessions"), 200));
        assertThat(listed.path("items")).hasSize(2);
        assertThat(listed.path("items").valueStream().map(item -> item.path("stageId").asString()))
                .containsOnly(f.stageId());
        expect(f.hr().put(f.legacy() + "/candidates/" + f.applicationId() + "/interview/session",
                assignment(f)), 405);
        readyBoth(f);
        JsonNode locked = json(expect(f.hr().get(f.legacy() + "/interview/assignment"), 200));
        assertThat(locked.path("locked").asBoolean()).isTrue();
        expect(f.hr().put(f.legacy() + "/interview/assignment", Map.of(
                "hrMemberId", f.practical().id(), "practicalMemberId", f.people().id(),
                "expectedVersion", assigned.path("version").asLong())), 409);
    }

    @Test
    @DisplayName("전형 배정을 바꾸면 지원자 전원의 담당이 바뀌고 이전 버전은 거절한다")
    void stageReassignmentUpdatesEveryCandidateAndChecksVersion() throws Exception {
        Fixture f = fixture(2, false);
        JsonNode first = json(expect(f.hr().put(f.admin(), assignment(f)), 200));
        JsonNode changed = json(expect(f.hr().put(f.admin(), Map.of(
                "hrMemberId", f.practical().id(), "practicalMemberId", f.people().id(),
                "expectedVersion", first.path("version").asLong())), 200));
        assertThat(changed.path("version").asLong()).isGreaterThan(first.path("version").asLong());
        JsonNode listed = json(expect(f.people().api().get("/api/interviewer/sessions"), 200));
        assertThat(listed.path("items")).hasSize(2);
        assertThat(listed.path("items").valueStream().map(item -> item.path("myRole").asString()))
                .containsOnly("PRACTICAL");
        expect(f.hr().put(f.admin(), Map.of("hrMemberId", f.people().id(),
                "practicalMemberId", f.practical().id(), "expectedVersion", first.path("version").asLong())), 409);
        expect(newHr().get(f.admin()), 404);
        String documentStage = recruits.getByStage(f.hr().companyId(), UUID.fromString(f.stageId()))
                .stages().getFirst().id().toString();
        expect(f.hr().put("/api/stages/" + documentStage + "/interview/assignment", assignment(f)), 409);
    }

    @Test
    @DisplayName("지원자가 없는 예정 전형에 배정한 면접관은 전형이 열리면 모든 지원자를 맡는다")
    void assignmentBeforeCandidatesArriveIsAppliedOnStageOpening() throws Exception {
        Fixture f = fixture(2, true);
        JsonNode assigned = json(expect(f.hr().get(f.legacy() + "/interview/assignment"), 200));
        assertThat(assigned.path("hrMemberId").asString()).isEqualTo(f.people().id().toString());
        JsonNode listed = json(expect(f.people().api().get("/api/interviewer/sessions"), 200));
        assertThat(listed.path("items")).hasSize(2);
        expect(f.practical().api().get(f.workspace()), 200);
    }

    @Test
    @DisplayName("인사와 실무 개인 메모는 같은 초기 버전으로 동시에 저장해도 모두 성공한다")
    void personalMemoVersionsAreIndependent() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        readyBoth(f);
        JsonNode started = json(expect(f.people().api().get(f.workspace()), 200));
        long version = started.path("personalMemoVersion").asLong();
        assertThat(version).isZero();
        assertThat(started.path("session").path("version").asLong()).isGreaterThan(version);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> hr = executor.submit(() -> f.people().api().put(f.workspace() + "/memo",
                    Map.of("text", "PRIVATE-HR-MEMO", "expectedVersion", version)).statusCode());
            Future<Integer> practical = executor.submit(() -> f.practical().api().put(f.workspace() + "/memo",
                    Map.of("text", "PRIVATE-PRACTICAL-MEMO", "expectedVersion", version)).statusCode());
            assertThat(List.of(hr.get(), practical.get())).containsExactly(200, 200);
        }
        JsonNode hr = json(expect(f.people().api().get(f.workspace()), 200));
        JsonNode practical = json(expect(f.practical().api().get(f.workspace()), 200));
        assertThat(hr.path("personalMemo").asString()).isEqualTo("PRIVATE-HR-MEMO");
        assertThat(practical.path("personalMemo").asString()).isEqualTo("PRIVATE-PRACTICAL-MEMO");
        assertThat(hr.path("personalMemoVersion").asLong()).isEqualTo(version + 1);
        assertThat(practical.path("personalMemoVersion").asLong()).isEqualTo(version + 1);
        assertThat(hr.toString()).doesNotContain("PRIVATE-PRACTICAL-MEMO", "practicalMemoVersion");
        assertThat(practical.toString()).doesNotContain("PRIVATE-HR-MEMO", "hrMemoVersion");
        expect(f.people().api().put(f.workspace() + "/memo", Map.of("text", "인사 수정",
                "expectedVersion", hr.path("personalMemoVersion").asLong())), 200);
        expect(f.practical().api().put(f.workspace() + "/memo", Map.of("text", "실무 수정",
                "expectedVersion", practical.path("personalMemoVersion").asLong())), 200);
    }

    @Test
    @DisplayName("같은 개인 메모를 동일 버전으로 동시에 저장하면 하나만 성공하고 나머지는 충돌이다")
    void concurrentPersonalMemoWritesCannotOverwriteEachOther() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        readyBoth(f);
        JsonNode started = json(expect(f.people().api().get(f.workspace()), 200));
        long version = started.path("personalMemoVersion").asLong();
        JsonNode wrongVersion = json(expect(f.people().api().put(f.workspace() + "/memo", Map.of("text", "세션 버전 오용",
                "expectedVersion", started.path("session").path("version").asLong())), 409));
        assertThat(wrongVersion.path("code").asString()).isEqualTo("MEMO_CONFLICT");
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> one = executor.submit(() -> f.people().api().put(f.workspace() + "/memo",
                    Map.of("text", "첫 번째 인사 메모", "expectedVersion", version)).statusCode());
            Future<Integer> two = executor.submit(() -> f.people().api().put(f.workspace() + "/memo",
                    Map.of("text", "두 번째 인사 메모", "expectedVersion", version)).statusCode());
            assertThat(List.of(one.get(), two.get())).containsExactlyInAnyOrder(200, 409);
        }
        JsonNode current = json(expect(f.people().api().get(f.workspace()), 200));
        assertThat(current.path("personalMemo").asString()).isIn("첫 번째 인사 메모", "두 번째 인사 메모");
        assertThat(current.path("personalMemoVersion").asLong()).isEqualTo(version + 1);
        expect(f.people().api().put(f.workspace() + "/memo", Map.of("text", "최신 인사 메모",
                "expectedVersion", current.path("personalMemoVersion").asLong())), 200);
    }

    @Test
    @DisplayName("공유 기록 API만 제거하고 개인 메모는 계속 제공한다")
    void sharedNotesAreRemovedWhilePersonalMemosRemain() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        String notes = f.workspace() + "/shared-notes";
        assertThat(f.people().api().get(notes).statusCode()).isIn(404, 405);
        assertThat(f.people().api().put(notes + "/me", Map.of("text", "옛 공유 기록", "expectedVersion", 0))
                .statusCode()).isIn(404, 405);
        assertThat(f.hr().get(f.legacy() + "/candidates/" + f.applicationId()
                + "/interview/shared-notes").statusCode()).isIn(404, 405);
        assertThat(json(expect(f.people().api().get(f.workspace()), 200)).has("personalMemo")).isTrue();
    }

    @Test
    @DisplayName("같은 면접 일시의 지원자는 함께 준비 · 시작 · 종료하고, 일정이 없는 지원자는 시작할 수 없다")
    void sameTimeApplicantsInterviewTogether() throws Exception {
        Fixture f = fixture(3, false);
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        List<String> ids = applicants(f);
        String a = ids.get(0);
        String b = ids.get(1);
        String unscheduled = ids.get(2);
        schedule(f, a, SLOT);
        schedule(f, b, SLOT);
        // HR 전형 화면은 면접 일시 목록으로 지원자를 시간별로 나눈다 (일정이 없는 지원자는 없다)
        JsonNode schedules = json(expect(f.hr().get(f.legacy() + "/interview/schedules"), 200));
        assertThat(schedules.valueStream().map(row -> row.path("applicationId").asString()))
                .containsExactlyInAnyOrder(a, b);
        expect(f.practical().api().get(f.legacy() + "/interview/schedules"), 403);

        assertThat(code(f.practical().api().post(room(f, unscheduled) + "/ready", null), 409))
                .isEqualTo("INTERVIEW_NOT_SCHEDULED");
        JsonNode group = json(expect(f.practical().api().get(room(f, a)), 200)).path("group");
        assertThat(Instant.parse(group.path("scheduledAt").asString())).isEqualTo(SLOT);
        assertThat(group.path("status").asString()).isEqualTo("SCHEDULED");
        assertThat(group.path("members").valueStream().map(member -> member.path("applicationId").asString()))
                .containsExactlyInAnyOrder(a, b);
        assertThat(group.path("members").valueStream().allMatch(member -> member.path("blocker").isNull()))
                .isTrue();
        assertThat(json(expect(f.practical().api().get(room(f, unscheduled)), 200)).path("group")
                .path("scheduledAt").isNull()).isTrue();

        // 한 지원자 화면에서 누른 준비 완료는 같은 시간 면접자 모두에 대한 준비다
        expect(f.practical().api().post(room(f, a) + "/ready", null), 200);
        JsonNode fromB = json(expect(f.people().api().get(room(f, b) + "/attendance"), 200));
        assertThat(fromB.path("attendees").valueStream()
                .filter(person -> person.path("role").asString().equals("PRACTICAL")).findFirst().orElseThrow()
                .path("ready").asBoolean()).isTrue();
        assertThat(status(f, a)).isEqualTo("SCHEDULED");
        expect(f.people().api().post(room(f, b) + "/ready", null), 200);
        assertThat(status(f, a)).isEqualTo("IN_PROGRESS");
        assertThat(status(f, b)).isEqualTo("IN_PROGRESS");
        assertThat(status(f, unscheduled)).isEqualTo("SCHEDULED");

        JsonNode progress = json(expect(f.hr().get(f.legacy() + "/interview/sessions"), 200));
        assertThat(progress.valueStream().filter(row -> !row.path("scheduledAt").isNull())
                .map(row -> row.path("applicationId").asString())).containsExactlyInAnyOrder(a, b);
        assertThat(progress.valueStream().filter(row -> !row.path("scheduledAt").isNull())
                .map(row -> row.path("startedAt").asString()).distinct()).hasSize(1);
        JsonNode started = json(expect(f.hr().get("/api/companies/current/interviews/started"), 200));
        assertThat(started).hasSize(1);
        assertThat(started.get(0).path("applicantNames")).hasSize(2);
        assertThat(Instant.parse(started.get(0).path("scheduledAt").asString())).isEqualTo(SLOT);

        // 시작한 시간에는 끼워 넣을 수 없고, 시작한 면접은 옮길 수 없다
        assertThat(code(scheduleRequest(f, unscheduled, SLOT), 409)).isEqualTo("INTERVIEW_SLOT_STARTED");
        assertThat(code(scheduleRequest(f, a, LATER), 409)).isEqualTo("INTERVIEW_STARTED");

        // 한 지원자 화면에서 누른 면접 종료는 같은 시간 면접자 모두에 대해 그 면접관이 마친 것이다
        expect(f.people().api().post(room(f, b) + "/end", null), 200);
        assertThat(status(f, a)).isEqualTo("IN_PROGRESS");
        JsonNode fromA = json(expect(f.practical().api().get(room(f, a) + "/attendance"), 200));
        assertThat(fromA.path("attendees").valueStream().map(person -> person.path("role").asString() + ":"
                + person.path("ended").asBoolean())).containsExactly("HR:true", "PRACTICAL:false");
        // 두 면접관이 모두 마치면 같은 시간 면접자가 모두 끝난다
        expect(f.practical().api().post(room(f, a) + "/end", null), 200);
        assertThat(status(f, a)).isEqualTo("ENDED");
        assertThat(status(f, b)).isEqualTo("ENDED");
    }

    @Test
    @DisplayName("불참한 지원자는 빼고 시작하고, 시작한 뒤 불참을 되돌리면 진행 중인 면접에 함께한다")
    void absentApplicantsAreLeftOut() throws Exception {
        Fixture f = fixture(2, false);
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        List<String> ids = applicants(f);
        String a = ids.get(0);
        String b = ids.get(1);
        schedule(f, a, SLOT);
        schedule(f, b, SLOT);

        assertThat(json(expect(f.practical().api().post(room(f, b) + "/absent", null), 200))
                .path("session").path("status").asString()).isEqualTo("ABSENT");
        // 불참은 면접을 하지 않은 것이라 면접관 배정을 잠그지 않는다
        assertThat(json(expect(f.hr().get(f.admin()), 200)).path("locked").asBoolean()).isFalse();
        expect(f.practical().api().post(room(f, a) + "/ready", null), 200);
        expect(f.people().api().post(room(f, a) + "/ready", null), 200);
        assertThat(status(f, a)).isEqualTo("IN_PROGRESS");
        assertThat(status(f, b)).isEqualTo("ABSENT");

        JsonNode rejoined = json(expect(f.practical().api().delete(room(f, b) + "/absent"), 200));
        assertThat(rejoined.path("session").path("status").asString()).isEqualTo("IN_PROGRESS");
        assertThat(rejoined.path("session").path("startedAt").asString()).isEqualTo(
                json(expect(f.people().api().get(room(f, a)), 200)).path("session").path("startedAt").asString());

        // 답변을 기록한 지원자는 불참으로 둘 수 없다
        JsonNode question = question(rejoined, "PRACTICAL");
        expect(f.practical().api().put(answerPath(f, question.path("questionId").asString()),
                answer(question, "결제 원장을 직접 설계했어요")), 200);
        assertThat(code(f.practical().api().post(room(f, b) + "/absent", null), 409))
                .isEqualTo("INTERVIEW_ANSWERED");

        expect(f.people().api().post(room(f, a) + "/end", null), 200);
        expect(f.practical().api().post(room(f, b) + "/end", null), 200);
        assertThat(status(f, b)).isEqualTo("ENDED");
        assertThat(code(f.practical().api().post(room(f, b) + "/absent", null), 409)).isEqualTo("INTERVIEW_ENDED");
    }

    @Test
    @DisplayName("불참한 지원자를 다른 시간으로 옮기면 그 시간의 예정 면접자로 돌아온다")
    void reschedulingAnAbsentApplicantBringsThemBack() throws Exception {
        Fixture f = fixture(2, false);
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        List<String> ids = applicants(f);
        String a = ids.get(0);
        String b = ids.get(1);
        schedule(f, a, SLOT);
        schedule(f, b, SLOT);
        // 준비 완료한 뒤 함께 볼 사람이 바뀌면 그 지원자에 대한 준비는 거둔다
        expect(f.practical().api().post(room(f, a) + "/ready", null), 200);
        expect(f.practical().api().post(room(f, b) + "/absent", null), 200);
        schedule(f, b, LATER);
        assertThat(status(f, b)).isEqualTo("SCHEDULED");
        assertThat(json(expect(f.practical().api().get(room(f, b)), 200)).path("group").path("members"))
                .hasSize(1);

        expect(f.people().api().post(room(f, a) + "/ready", null), 200);
        assertThat(status(f, a)).isEqualTo("IN_PROGRESS");
        assertThat(status(f, b)).isEqualTo("SCHEDULED");
        assertThat(code(scheduleRequest(f, b, SLOT), 409)).isEqualTo("INTERVIEW_SLOT_STARTED");
    }

    @Test
    @DisplayName("면접관이 준비 완료한 동안과 면접이 시작된 뒤에는 질문을 다시 만들 수 없다")
    void questionsAreNotRegeneratedUnderReadyInterviewers() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        schedule(f, f.applicationId(), SLOT);
        String regenerate = f.legacy() + "/candidates/" + f.applicationId() + "/interview/questions/regenerate";

        // 면접관이 지금 질문을 보고 준비 완료했으면 바꾸지 않는다 (준비를 취소하면 다시 만들 수 있다)
        expect(f.practical().api().post(f.workspace() + "/ready", null), 200);
        assertThat(code(f.hr().post(regenerate, null), 409)).isEqualTo("INTERVIEWERS_READY");
        expect(f.practical().api().delete(f.workspace() + "/ready"), 200);
        expect(f.hr().post(regenerate, null), 202);
        applicants(f);

        readyBoth(f);
        assertThat(status(f, f.applicationId().toString())).isEqualTo("IN_PROGRESS");
        assertThat(code(f.hr().post(regenerate, null), 409)).isEqualTo("INTERVIEW_STARTED");
    }

    private Fixture fixture() throws Exception {
        return fixture(1, false);
    }

    private Fixture fixture(int count, boolean assignBeforeOpening) throws Exception {
        TestApi hr = newHr();
        Account people = account(hr.companyId(), MemberRole.INTERVIEWER);
        Account practical = account(hr.companyId(), MemberRole.INTERVIEWER);
        Account unassigned = account(hr.companyId(), MemberRole.HR);
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        if (assignBeforeOpening) {
            UUID stage = recruits.get(hr.companyId(), recruitmentId).stages().stream()
                    .filter(item -> item.type() == StageType.INTERVIEW).findFirst().orElseThrow().id();
            String assignmentPath = "/api/stages/" + stage + "/interview/assignment";
            expect(hr.put(assignmentPath, Map.of("hrMemberId", people.id(), "practicalMemberId", practical.id())), 200);
            assertThat(json(expect(people.api().get("/api/interviewer/sessions"), 200)).path("items")).isEmpty();
        }
        for (int i = 0; i < count; i++) {
            expect(anonymous().multipart(posting.applyPath(),
                    TestFixtures.form("candidate" + i + "@example.com", false)), 201);
        }
        Instant deadline = Instant.now().plusSeconds(15);
        UUID applicationId = null;
        while (Instant.now().isBefore(deadline)) {
            var found = applications.applicants(hr.companyId(), recruitmentId).stream()
                    .filter(applicant -> applicant.analysisStatus() == AnalysisStatus.DONE).toList();
            if (found.size() == count) {
                applicationId = found.getFirst().applicationId();
                break;
            }
            Thread.sleep(100);
        }
        assertThat(applicationId).isNotNull();
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", applications.applicants(hr.companyId(), recruitmentId).stream()
                        .map(com.hiremate.apply.ApplicantInfo::applicationId).toList(), "decision", "PASS")), 204);
        expect(hr.post(document + "/confirm", null), 200);
        expect(hr.post(document + "/notices/prepare", null), 200);
        expect(hr.post(document + "/notices/PASS/send", null), 200);
        String stage = json(expect(hr.post(document + "/finish", null), 200)).path("nextStageId").asString();
        Fixture f = new Fixture(hr, people, practical, unassigned, stage, applicationId);
        deadline = Instant.now().plusSeconds(15);
        while (Instant.now().isBefore(deadline)) {
            JsonNode card = json(expect(hr.get(f.legacy() + "/candidates/" + applicationId + "/interview"), 200));
            if (!card.path("questions").isEmpty()) {
                return f;
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Interview questions were not prepared.");
    }

    private Account account(UUID companyId, MemberRole role) throws Exception {
        String email = UUID.randomUUID() + "@example.com";
        String password = "test-interviewer-password";
        Member member = members.saveAndFlush(new Member(companyId, "면접관", email, passwords.encode(password), role));
        TestApi api = anonymous();
        api.login(email, password);
        return new Account(api, member.getId());
    }

    /** 면접 일시를 정하고 두 면접관이 [준비 완료]를 누른다. 배정된 면접관이 모두 준비 완료하면 면접이 바로 시작된다. */
    private static void readyBoth(Fixture f) throws Exception {
        schedule(f, f.applicationId(), SLOT);
        expect(f.practical().api().post(f.workspace() + "/ready", null), 200);
        expect(f.people().api().post(f.workspace() + "/ready", null), 200);
    }

    /** 테스트의 면접 시간. 같은 일시의 지원자는 한 면접으로 함께 시작하고 함께 끝낸다 */
    private static final Instant SLOT = Instant.parse("2026-11-20T05:00:00Z");

    private static final Instant LATER = Instant.parse("2026-11-20T07:00:00Z");

    private static HttpResponse<String> scheduleRequest(Fixture f, Object applicationId, Instant at) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("scheduledAt", at == null ? null : at.toString());
        body.put("interviewers", "");
        return f.hr().put(f.legacy() + "/candidates/" + applicationId + "/interview/schedule", body);
    }

    private static void schedule(Fixture f, Object applicationId, Instant at) throws Exception {
        expect(scheduleRequest(f, applicationId, at), 200);
    }

    private static String room(Fixture f, String applicationId) {
        return "/api/interviewer/sessions/" + f.stageId() + "/" + applicationId;
    }

    private static String status(Fixture f, String applicationId) throws Exception {
        return json(expect(f.people().api().get(room(f, applicationId)), 200)).path("session").path("status")
                .asString();
    }

    private static String code(HttpResponse<String> response, int status) {
        return json(expect(response, status)).path("code").asString();
    }

    /** 전형의 지원자들. 앞 전형 확정 때 미리 만드는 면접 질문이 다 들어올 때까지 기다린다 */
    private static List<String> applicants(Fixture f) throws Exception {
        List<String> ids = json(expect(f.hr().get(f.legacy() + "/interview/sessions"), 200)).valueStream()
                .map(row -> row.path("applicationId").asString()).sorted().toList();
        for (String id : ids) {
            Instant deadline = Instant.now().plusSeconds(15);
            while (Instant.now().isBefore(deadline) && (json(expect(f.hr().get(f.legacy() + "/candidates/" + id
                    + "/interview/preparing"), 200)).path("preparing").asBoolean() || json(expect(f.hr().get(
                            f.legacy() + "/candidates/" + id + "/interview"), 200)).path("questions").isEmpty())) {
                Thread.sleep(200);
            }
        }
        return ids;
    }

    private static Map<String, Object> assignment(Fixture f) {
        return Map.of("hrMemberId", f.people().id(), "practicalMemberId", f.practical().id());
    }

    private static JsonNode question(JsonNode workspace, String role) {
        return workspace.path("questions").valueStream().map(row -> row.path("question"))
                .filter(item -> item.path("interviewerRole").asString().equals(role)).findFirst().orElseThrow();
    }

    private static Map<String, Object> answer(JsonNode question, String text) {
        return Map.of("answer", text, "analyze", false, "expectedVersion", question.path("version").asLong());
    }

    private static String answerPath(Fixture f, String questionId) {
        return f.questionRoot() + questionId + "/answer";
    }

    private record Account(TestApi api, UUID id) {
    }

    /** hr는 채용 담당자(HR 계정), people은 인사 면접관 계정, practical은 실무 면접관 계정이다. */
    private record Fixture(TestApi hr, Account people, Account practical, Account unassigned, String stageId,
            UUID applicationId) {
        String legacy() {
            return "/api/stages/" + stageId;
        }

        String admin() {
            return legacy() + "/interview/assignment";
        }

        String workspace() {
            return "/api/interviewer/sessions/" + stageId + "/" + applicationId;
        }

        String questionRoot() {
            return "/api/interviewer/sessions/" + stageId + "/questions/";
        }
    }
}
