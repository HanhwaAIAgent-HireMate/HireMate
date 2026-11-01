package com.hiremate.auth;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.apply.ApplicationService;
import com.hiremate.auth.domain.Member;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.interview.InterviewQuestionDraft;
import com.hiremate.interview.InterviewService;
import com.hiremate.interview.InterviewerRole;
import java.time.Instant;
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
        enter(f);
        JsonNode started = json(expect(f.people().api().post(f.workspace() + "/start", null), 200));
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
                        current.path("session").path("version").asLong())), 200));
        assertThat(noted.path("personalMemo").asString()).isEqualTo("PRIVATE-HR-NOTE");
        String other = expect(f.practical().api().get(f.workspace()), 200).body();
        assertThat(other).doesNotContain("PRIVATE-HR-NOTE", "hrMemo", "practicalMemo");
        JsonNode ended = json(expect(f.practical().api().post(f.workspace() + "/end", null), 200));
        assertThat(ended.path("session").path("status").asString()).isEqualTo("ENDED");
        assertThat(ended.path("questions").valueStream().allMatch(row -> !row.path("canAnswer").asBoolean()))
                .isTrue();
        expect(f.practical().api().put(answerPath(f, jobId),
                Map.of("answer", "늦게 도착한 저장", "analyze", false, "expectedVersion", version)), 409);
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
        enter(f);
        expect(f.people().api().post(f.workspace() + "/start", null), 409);
        expect(f.hr().put(f.legacy() + "/interview/questions/" + questionId + "/role",
                Map.of("interviewerRole", "PRACTICAL")), 200);
        expect(f.people().api().post(f.workspace() + "/start", null), 200);
        assertThat(assigned.path("hrMemberId").asString()).isEqualTo(f.people().id().toString());
        expect(f.hr().put(f.legacy() + "/candidates/" + f.applicationId() + "/interview/session",
                Map.of("hrMemberId", f.practical().id(), "practicalMemberId", f.people().id(),
                        "expectedVersion", assigned.path("version").asLong())), 409);
    }

    @Test
    @DisplayName("동일 버전의 동시 자동 저장은 하나만 성공하고 나머지는 충돌을 반환한다")
    void concurrentAutosavesCannotOverwriteEachOther() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        enter(f);
        JsonNode started = json(expect(f.practical().api().post(f.workspace() + "/start", null), 200));
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
        enter(f);
        expect(f.people().api().post(f.workspace() + "/start", null), 200);
        JsonNode rejected = json(expect(f.hr().post(f.legacy() + "/confirm", null), 409));
        assertThat(rejected.path("code").asString()).isEqualTo("INTERVIEW_IN_PROGRESS");
        expect(f.people().api().post(f.workspace() + "/end", null), 200);
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
        enter(f);
        expect(f.people().api().post(f.workspace() + "/start", null), 200);
        expect(f.hr().put(root + "/role", Map.of("interviewerRole", "HR")), 409);
    }

    @Test
    @DisplayName("면접 시작과 전형 확정이 동시에 도착하면 한 작업만 성공한다")
    void concurrentStartAndConfirmationCannotBothSucceed() throws Exception {
        Fixture f = fixture();
        expect(f.hr().put(f.admin(), assignment(f)), 200);
        enter(f);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> start = executor.submit(() ->
                    f.people().api().post(f.workspace() + "/start", null).statusCode());
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

    private Fixture fixture() throws Exception {
        TestApi hr = newHr();
        Account people = account(hr.companyId(), MemberRole.INTERVIEWER);
        Account practical = account(hr.companyId(), MemberRole.INTERVIEWER);
        Account unassigned = account(hr.companyId(), MemberRole.HR);
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        expect(anonymous().multipart(posting.applyPath(), TestFixtures.form("candidate@example.com", false)), 201);
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plusSeconds(15);
        UUID applicationId = null;
        while (Instant.now().isBefore(deadline)) {
            var found = applications.applicants(hr.companyId(), recruitmentId).stream()
                    .filter(applicant -> applicant.documentScore() != null).findFirst();
            if (found.isPresent()) {
                applicationId = found.get().applicationId();
                break;
            }
            Thread.sleep(100);
        }
        assertThat(applicationId).isNotNull();
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        String document = "/api/stages/" + closed.path("stages").get(0).path("id").asString();
        expect(hr.post(document + "/decisions",
                Map.of("applicationIds", List.of(applicationId), "decision", "PASS")), 204);
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

    /** 두 면접관이 면접관 모드에 입장한다. 면접은 배정된 면접관이 모두 입장해야 시작할 수 있다. */
    private static void enter(Fixture f) throws Exception {
        expect(f.people().api().post(f.workspace() + "/enter", null), 200);
        expect(f.practical().api().post(f.workspace() + "/enter", null), 200);
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
            return legacy() + "/candidates/" + applicationId + "/interview/session";
        }

        String workspace() {
            return "/api/interviewer/sessions/" + stageId + "/" + applicationId;
        }

        String questionRoot() {
            return "/api/interviewer/sessions/" + stageId + "/questions/";
        }
    }
}
