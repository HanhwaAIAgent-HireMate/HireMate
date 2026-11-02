package com.hiremate.interview;

import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewQuestion;
import com.hiremate.interview.domain.InterviewQuestionRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageConfirmed;
import com.hiremate.recruit.StageStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 면접관 페이지의 배정·권한·진행 상태. 호출자의 ID는 인증 진입 계층에서만 받는다. */
@Service
public class InterviewSessions {

    private final InterviewSessionRepository sessions;
    private final InterviewQuestionRepository questions;
    private final InterviewService interviews;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final InterviewAttendances attendances;
    private final ApplicationEventPublisher events;

    public InterviewSessions(InterviewSessionRepository sessions, InterviewQuestionRepository questions,
            InterviewService interviews, RecruitService recruits, ApplicationService applications,
            InterviewAttendances attendances, ApplicationEventPublisher events) {
        this.attendances = attendances;
        this.events = events;
        this.sessions = sessions;
        this.questions = questions;
        this.interviews = interviews;
        this.recruits = recruits;
        this.applications = applications;
    }

    @Transactional(readOnly = true)
    public InterviewAssignment assignment(UUID companyId, UUID stageId, UUID applicationId) {
        interviews.preparationView(companyId, stageId, applicationId);
        return toAssignment(find(companyId, stageId, applicationId));
    }

    @Transactional(readOnly = true)
    public AssignedInterviews list(UUID companyId, UUID memberId, int page, int size) {
        if (page < 0 || size < 1 || size > 50) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_PAGE", "Use a nonnegative page and size 1 to 50.");
        }
        var found = sessions.assigned(companyId, memberId, PageRequest.of(page, size));
        List<AssignedInterview> items = found.stream().map(session -> {
            RecruitmentInfo recruit = recruits.getByStage(companyId, session.getStageId());
            InterviewView view = interviews.preparationView(companyId, session.getStageId(),
                    session.getApplicationId());
            String name = applications.applicants(companyId, List.of(session.getApplicationId())).getFirst().name();
            return new AssignedInterview(session.getStageId(), session.getApplicationId(), recruit.title(),
                    recruit.stage(session.getStageId()).orElseThrow().name(), name, view.schedule(),
                    session.roleOf(memberId), session.getStatus(), recruit.id());
        }).toList();
        return new AssignedInterviews(items, found.getTotalElements(), page, size);
    }

    /** 면접관 모드의 자료 읽기 권한: 이 지원자의 이 면접에 배정됐나. */
    @Transactional(readOnly = true)
    public boolean assigned(UUID companyId, UUID memberId, UUID stageId, UUID applicationId) {
        return sessions.assignedTo(companyId, memberId, stageId, applicationId);
    }

    /** 면접관 Chat 탭 경로의 권한: 이 전형에서 한 명이라도 배정됐나. */
    @Transactional(readOnly = true)
    public boolean assignedInStage(UUID companyId, UUID memberId, UUID stageId) {
        return !roles(companyId, memberId, stageId).isEmpty();
    }

    /** 이 전형에서 계정이 배정된 지원자와 그 지원자에서 맡은 담당. 면접관 Chat은 이 지원자만 본다. */
    @Transactional(readOnly = true)
    public Map<UUID, InterviewerRole> roles(UUID companyId, UUID memberId, UUID stageId) {
        Map<UUID, InterviewerRole> roles = new LinkedHashMap<>();
        sessions.findByStageIdAndCompanyId(stageId, companyId).forEach(session -> {
            InterviewerRole role = session.roleOf(memberId);
            if (role != null) {
                roles.put(session.getApplicationId(), role);
            }
        });
        return roles;
    }

    /** 지원 문서처럼 채용 단위 경로의 읽기 권한: 이 지원자의 면접 하나에라도 배정됐나. */
    @Transactional(readOnly = true)
    public boolean assignedToApplication(UUID companyId, UUID memberId, UUID applicationId) {
        return sessions.assignedToApplication(companyId, memberId, applicationId);
    }

    @Transactional(readOnly = true)
    public InterviewerWorkspace view(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = find(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        return workspace(session, memberId);
    }

    /**
     * 면접관의 [준비 완료]. 배정된 두 면접관이 모두 준비 완료하고 접속 중이면 그 자리에서 면접을 시작한다.
     * 질문이 시작할 수 있는 상태가 아니면 준비 완료를 받지 않는다 (시작할 수 없는 준비가 남지 않게 한다).
     */
    @Transactional
    public InterviewAttendances.Attendance ready(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        requireActive(companyId, stageId);
        if (session.getStatus() == InterviewSessionStatus.SCHEDULED) {
            requireStartable(companyId, stageId, applicationId);
            attendances.markReady(session, memberId);
            if (attendances.ready(session)) {
                session.start();
                sessions.flush();
            }
            changed(companyId, stageId, applicationId);
        }
        return attendances.attendance(companyId, stageId, applicationId, memberId);
    }

    /** 시작 전에 [준비 완료]를 거둔다. 시작한 면접은 그대로 둔다. */
    @Transactional
    public InterviewAttendances.Attendance cancelReady(UUID companyId, UUID stageId, UUID applicationId,
            UUID memberId) {
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        if (session.getStatus() == InterviewSessionStatus.SCHEDULED) {
            attendances.clearReady(session, memberId);
            changed(companyId, stageId, applicationId);
        }
        return attendances.attendance(companyId, stageId, applicationId, memberId);
    }

    /** HR 알림: 최근 7일 안에 시작한 면접, 최근 것부터 20개. */
    @Transactional(readOnly = true)
    public List<StartedInterview> recentStarts(UUID companyId) {
        Instant since = Instant.now().minus(Duration.ofDays(7));
        return sessions.startedSince(companyId, since, PageRequest.of(0, 20)).stream().map(session -> {
            RecruitmentInfo recruit = recruits.getByStage(companyId, session.getStageId());
            String name = applications.applicants(companyId, List.of(session.getApplicationId())).getFirst().name();
            return new StartedInterview(session.getStageId(), session.getApplicationId(), recruit.id(),
                    recruit.title(), recruit.stage(session.getStageId()).orElseThrow().name(), name,
                    session.getStartedAt());
        }).toList();
    }

    /** 면접을 시작할 수 있는 질문 구성인가: 생성이 끝났고, 모든 질문에 담당이 있고, 담당 규칙을 지킨다. */
    private void requireStartable(UUID companyId, UUID stageId, UUID applicationId) {
        if (interviews.preparing(companyId, stageId, applicationId)) {
            throw conflict("QUESTIONS_PREPARING", "Wait for question preparation to finish.");
        }
        List<InterviewQuestion> card = card(companyId, stageId, applicationId);
        if (card.isEmpty() || card.stream().anyMatch(question -> question.getInterviewerRole() == null)) {
            throw conflict("QUESTION_OWNER_REQUIRED", "Assign all question owners before starting.");
        }
        for (InterviewQuestion question : card) {
            if (InterviewService.INTRO.equals(question.getText())
                    && question.getInterviewerRole() != InterviewerRole.HR) {
                throw conflict("INTRO_OWNER", "HR records the common introduction.");
            }
            if (question.getParentQuestionId() != null && card.stream().anyMatch(parent ->
                    parent.getId().equals(question.getParentQuestionId())
                            && parent.getInterviewerRole() != question.getInterviewerRole())) {
                throw conflict("FOLLOW_UP_OWNER", "A follow-up must keep its parent's owner.");
            }
        }
    }

    @Transactional
    public InterviewerWorkspace end(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        if (session.getStatus() == InterviewSessionStatus.SCHEDULED) {
            throw conflict("INTERVIEW_NOT_STARTED", "Start the interview first.");
        }
        if (session.getStatus() == InterviewSessionStatus.IN_PROGRESS) {
            requireActive(companyId, stageId);
            interviews.submitPendingAnswers(companyId, stageId, applicationId);
            session.end();
            sessions.flush();
            changed(companyId, stageId, applicationId);
        }
        return workspace(session, memberId);
    }

    /** 결과 확정 트랜잭션 안에서 검사해 진행 중인 면접이 있으면 확정도 롤백한다. */
    @EventListener
    public void on(StageConfirmed event) {
        if (sessions.existsByStageIdAndCompanyIdAndStatus(event.stageId(), event.companyId(),
                InterviewSessionStatus.IN_PROGRESS)) {
            throw conflict("INTERVIEW_IN_PROGRESS", "End all interviews before confirming the stage results.");
        }
        sessions.findByStageIdAndCompanyId(event.stageId(), event.companyId())
                .forEach(session -> changed(event.companyId(), event.stageId(), session.getApplicationId()));
    }

    /** 개인 메모만 반환한다. 상대 면접관의 메모는 API에 포함하지 않는다. */
    @Transactional
    public InterviewerWorkspace memo(UUID companyId, UUID stageId, UUID applicationId, UUID memberId, String memo,
            long expectedVersion) {
        InterviewSession session = lock(companyId, stageId, applicationId);
        InterviewerRole role = requireAssigned(session, memberId);
        requireRunning(session);
        requireActive(companyId, stageId);
        if (session.memoVersion(role) != expectedVersion) {
            throw conflict("MEMO_CONFLICT", "Reload the latest personal memo before saving.");
        }
        session.memo(role, memo);
        sessions.flush();
        return workspace(session, memberId);
    }

    /** HR 콘솔도 배정된 면접이 있으면 같은 권한·상태 검사를 거친다. */
    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, UUID memberId, String answer,
            boolean analyze, Long expectedVersion, boolean assignmentRequired) {
        recruits.lockStage(companyId, stageId);
        InterviewQuestion question = question(companyId, stageId, questionId);
        InterviewSession session = writeAccess(companyId, stageId, question, memberId, assignmentRequired);
        if (session != null && expectedVersion == null) {
            throw conflict("ANSWER_VERSION_REQUIRED", "Send the displayed answer version.");
        }
        changed(companyId, stageId, question.getApplicationId());
        return interviews.answer(companyId, stageId, questionId, answer, analyze, expectedVersion);
    }

    @Transactional
    public InterviewView addQuestion(UUID companyId, UUID stageId, UUID applicationId, UUID memberId,
            String text, InterviewerRole role, boolean assignmentRequired) {
        InterviewSession session = sessions.lock(companyId, stageId, applicationId).orElse(null);
        if (session == null && assignmentRequired) {
            throw notFound();
        }
        if (session != null) {
            if (role == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "QUESTION_OWNER_REQUIRED", "Choose a question owner.");
            }
            if (assignmentRequired || session.getStatus() != InterviewSessionStatus.SCHEDULED) {
                InterviewerRole actual = requireAssigned(session, memberId);
                requireRunning(session);
                requireActive(companyId, stageId);
                if (role != actual) {
                    throw forbidden();
                }
            }
        }
        if (InterviewService.INTRO.equals(text.strip()) && role != InterviewerRole.HR) {
            throw conflict("INTRO_OWNER", "HR records the common introduction.");
        }
        return interviews.addManualQuestion(companyId, stageId, applicationId, text, role);
    }

    @Transactional
    public InterviewView followUp(UUID companyId, UUID stageId, UUID questionId, UUID memberId, String text,
            QuestionSource source, String check, boolean assignmentRequired) {
        InterviewQuestion parent = question(companyId, stageId, questionId);
        writeAccess(companyId, stageId, parent, memberId, assignmentRequired);
        changed(companyId, stageId, parent.getApplicationId());
        return interviews.addFollowUp(companyId, stageId, questionId, text, source, check);
    }

    @Transactional
    public InterviewView delete(UUID companyId, UUID stageId, UUID questionId, UUID memberId,
            boolean assignmentRequired) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        InterviewSession planned = sessions.lock(companyId, stageId, question.getApplicationId()).orElse(null);
        if (!assignmentRequired && planned != null && planned.getStatus() == InterviewSessionStatus.SCHEDULED) {
            if (answeredTree(question, card(companyId, stageId, question.getApplicationId()))) {
                throw conflict("QUESTION_ANSWERED", "Recorded answers cannot be removed from an assigned interview.");
            }
            changed(companyId, stageId, question.getApplicationId());
            return interviews.deleteQuestion(companyId, stageId, questionId);
        }
        InterviewSession session = writeAccess(companyId, stageId, question, memberId, assignmentRequired);
        if (session != null && answeredTree(question, card(companyId, stageId, question.getApplicationId()))) {
            throw conflict("QUESTION_ANSWERED", "Recorded answers cannot be removed in interviewer mode.");
        }
        changed(companyId, stageId, question.getApplicationId());
        return interviews.deleteQuestion(companyId, stageId, questionId);
    }

    @Transactional
    public void requireQuestionWrite(UUID companyId, UUID stageId, UUID questionId, UUID memberId,
            boolean assignmentRequired) {
        writeAccess(companyId, stageId, question(companyId, stageId, questionId), memberId, assignmentRequired);
    }

    private InterviewSession writeAccess(UUID companyId, UUID stageId, InterviewQuestion question, UUID memberId,
            boolean assignmentRequired) {
        InterviewSession session = sessions.lock(companyId, stageId, question.getApplicationId()).orElse(null);
        if (session == null) {
            if (assignmentRequired) {
                throw notFound();
            }
            return null;
        }
        InterviewerRole role = requireAssigned(session, memberId);
        requireRunning(session);
        requireActive(companyId, stageId);
        if (question.getInterviewerRole() != role) {
            throw forbidden();
        }
        return session;
    }

    private InterviewerWorkspace workspace(InterviewSession session, UUID memberId) {
        UUID companyId = session.getCompanyId();
        UUID stageId = session.getStageId();
        InterviewerRole role = requireAssigned(session, memberId);
        InterviewView view = interviews.preparationView(companyId, stageId, session.getApplicationId());
        boolean active = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status()
                == StageStatus.ACTIVE;
        List<InterviewerQuestionAccess> questions = view.questions().stream()
                .sorted(Comparator.comparing(question -> question.interviewerRole() != role))
                .map(question -> {
                    String reason = question.interviewerRole() == null ? "담당 미지정"
                            : question.interviewerRole() != role ? "다른 면접관 담당"
                            : !active ? "진행 중인 전형이 아님"
                            : session.getStatus() == InterviewSessionStatus.SCHEDULED ? "면접 시작 전"
                            : session.getStatus() == InterviewSessionStatus.ENDED ? "면접 종료" : null;
                    boolean canFollowUp = reason == null && !question.answer().isBlank()
                            && !hasChild(question, view.questions()) && depth(question, view.questions()) < 2;
                    return new InterviewerQuestionAccess(question, reason == null, canFollowUp,
                            reason == null && !answeredView(question, view.questions()), reason);
                }).toList();
        return new InterviewerWorkspace(toAssignment(session), role, session.memo(role), session.memoVersion(role),
                questions, view.previous(), view.schedule());
    }

    private static boolean answeredView(InterviewView.Question question, List<InterviewView.Question> card) {
        return !question.answer().isBlank() || card.stream()
                .filter(child -> question.questionId().equals(child.parentQuestionId()))
                .anyMatch(child -> answeredView(child, card));
    }

    private static boolean answeredTree(InterviewQuestion question, List<InterviewQuestion> card) {
        return !question.getAnswer().isBlank() || card.stream()
                .filter(child -> question.getId().equals(child.getParentQuestionId()))
                .anyMatch(child -> answeredTree(child, card));
    }

    private static boolean hasChild(InterviewView.Question question, List<InterviewView.Question> card) {
        return card.stream().anyMatch(item -> question.questionId().equals(item.parentQuestionId()));
    }

    private static int depth(InterviewView.Question question, List<InterviewView.Question> card) {
        if (question.parentQuestionId() == null) {
            return 0;
        }
        return 1 + card.stream().filter(item -> item.questionId().equals(question.parentQuestionId()))
                .findFirst().map(parent -> depth(parent, card)).orElse(0);
    }

    private void requireActive(UUID companyId, UUID stageId) {
        if (recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status() != StageStatus.ACTIVE) {
            throw conflict("STAGE_NOT_ACTIVE", "The interview stage is not active.");
        }
    }

    private static void requireRunning(InterviewSession session) {
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS) {
            throw conflict("INTERVIEW_NOT_RUNNING", "The interview must be in progress.");
        }
    }

    private static InterviewerRole requireAssigned(InterviewSession session, UUID memberId) {
        InterviewerRole role = session.roleOf(memberId);
        if (role == null) {
            throw forbidden();
        }
        return role;
    }

    private InterviewSession find(UUID companyId, UUID stageId, UUID applicationId) {
        return sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .orElseThrow(InterviewSessions::notFound);
    }

    private InterviewSession lock(UUID companyId, UUID stageId, UUID applicationId) {
        return sessions.lock(companyId, stageId, applicationId).orElseThrow(InterviewSessions::notFound);
    }

    private InterviewQuestion question(UUID companyId, UUID stageId, UUID questionId) {
        return questions.findByIdAndStageIdAndCompanyId(questionId, stageId, companyId)
                .orElseThrow(InterviewSessions::notFound);
    }

    private List<InterviewQuestion> card(UUID companyId, UUID stageId, UUID applicationId) {
        return questions.findByStageIdAndApplicationIdAndCompanyIdOrderBySeq(stageId, applicationId, companyId);
    }

    private static InterviewAssignment toAssignment(InterviewSession session) {
        return new InterviewAssignment(session.getStageId(), session.getApplicationId(), session.getHrMemberId(),
                session.getPracticalMemberId(), session.getStatus(), session.getStartedAt(), session.getEndedAt(),
                session.getVersion());
    }

    /** 열어 둔 면접관 · HR 화면에 알린다. 저장이 끝난 뒤에 보낸다 (InterviewLive). */
    private void changed(UUID companyId, UUID stageId, UUID applicationId) {
        events.publishEvent(new InterviewSessionChanged(companyId, stageId, applicationId));
    }

    private static ApiException forbidden() {
        return new ApiException(HttpStatus.FORBIDDEN, "INTERVIEW_ACCESS_DENIED",
                "Only the assigned interviewer can edit this question.");
    }

    private static ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_SESSION_NOT_FOUND", "Interview session not found.");
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }

    public record InterviewAssignment(UUID stageId, UUID applicationId, UUID hrMemberId, UUID practicalMemberId,
            InterviewSessionStatus status, @Schema(nullable = true) Instant startedAt,
            @Schema(nullable = true) Instant endedAt, long version) {
    }

    public record InterviewerQuestionAccess(InterviewView.Question question, boolean canAnswer,
            boolean canRequestFollowUp,
            boolean canDelete, @Schema(nullable = true) String readOnlyReason) {
    }

    public record InterviewerWorkspace(InterviewAssignment session, InterviewerRole myRole, String personalMemo,
            long personalMemoVersion,
            List<InterviewerQuestionAccess> questions,
            List<InterviewView.PreviousInterview> previous,
            @Schema(nullable = true) InterviewView.Schedule schedule) {
    }

    public record AssignedInterview(UUID stageId, UUID applicationId, String recruitmentTitle, String stageName,
            String applicantName, @Schema(nullable = true) InterviewView.Schedule schedule,
            InterviewerRole myRole, InterviewSessionStatus status, UUID recruitmentId) {
    }

    public record AssignedInterviews(List<AssignedInterview> items, long total, int page, int size) {
    }

    /** HR 알림 한 줄: 시작한 면접. */
    public record StartedInterview(UUID stageId, UUID applicationId, UUID recruitmentId, String recruitmentTitle,
            String stageName, String applicantName, Instant startedAt) {
    }
}
