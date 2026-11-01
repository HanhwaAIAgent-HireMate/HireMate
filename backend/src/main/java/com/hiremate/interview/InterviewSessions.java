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
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
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

    public InterviewSessions(InterviewSessionRepository sessions, InterviewQuestionRepository questions,
            InterviewService interviews, RecruitService recruits, ApplicationService applications) {
        this.sessions = sessions;
        this.questions = questions;
        this.interviews = interviews;
        this.recruits = recruits;
        this.applications = applications;
    }

    /** 인증 모듈이 두 계정의 기업 소속을 확인한 뒤 HR 관리 경로에서만 호출한다. */
    @Transactional
    public InterviewAssignment assign(UUID companyId, UUID stageId, UUID applicationId, UUID hrMemberId,
            UUID practicalMemberId, Long expectedVersion) {
        recruits.lockStage(companyId, stageId);
        InterviewView view = interviews.preparationView(companyId, stageId, applicationId);
        StageStatus stageStatus = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status();
        if (stageStatus != StageStatus.PENDING && stageStatus != StageStatus.ACTIVE) {
            throw conflict("STAGE_CLOSED", "The interview stage is closed.");
        }
        if (hrMemberId.equals(practicalMemberId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "DISTINCT_INTERVIEWERS", "Assign two different members.");
        }
        InterviewSession session = sessions.lock(companyId, stageId, applicationId).orElse(null);
        if (session == null) {
            session = new InterviewSession(companyId, stageId, applicationId, hrMemberId, practicalMemberId);
        } else {
            if (session.getStatus() != InterviewSessionStatus.SCHEDULED
                    || view.questions().stream().anyMatch(question -> !question.answer().isBlank())) {
                throw conflict("INTERVIEW_STARTED", "Interviewer assignments are locked after recording starts.");
            }
            if (expectedVersion == null || expectedVersion != session.getVersion()) {
                throw conflict("SESSION_CONFLICT", "Reload the latest interview assignment.");
            }
            session.assign(hrMemberId, practicalMemberId);
        }
        return toAssignment(sessions.saveAndFlush(session));
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
                    session.roleOf(memberId), session.getStatus());
        }).toList();
        return new AssignedInterviews(items, found.getTotalElements(), page, size);
    }

    @Transactional(readOnly = true)
    public InterviewerWorkspace view(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        InterviewSession session = find(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        return workspace(session, memberId);
    }

    @Transactional
    public InterviewerWorkspace start(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        requireActive(companyId, stageId);
        if (session.getStatus() == InterviewSessionStatus.ENDED) {
            throw conflict("INTERVIEW_ENDED", "The interview has ended.");
        }
        if (session.getStatus() == InterviewSessionStatus.SCHEDULED) {
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
            session.start();
            sessions.flush();
        }
        return workspace(session, memberId);
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
    }

    /** 개인 메모만 반환한다. 상대 면접관의 메모는 API에 포함하지 않는다. */
    @Transactional
    public InterviewerWorkspace memo(UUID companyId, UUID stageId, UUID applicationId, UUID memberId, String memo,
            long expectedVersion) {
        InterviewSession session = lock(companyId, stageId, applicationId);
        InterviewerRole role = requireAssigned(session, memberId);
        requireRunning(session);
        requireActive(companyId, stageId);
        if (session.getVersion() != expectedVersion) {
            throw conflict("SESSION_CONFLICT", "Reload the latest personal memo before saving.");
        }
        session.memo(role, memo);
        sessions.flush();
        return workspace(session, memberId);
    }

    /** HR 콘솔도 배정된 면접이 있으면 같은 권한·상태 검사를 거친다. */
    @Transactional
    public InterviewView answer(UUID companyId, UUID stageId, UUID questionId, UUID memberId, String answer,
            boolean analyze, Long expectedVersion, boolean assignmentRequired) {
        InterviewQuestion question = question(companyId, stageId, questionId);
        InterviewSession session = writeAccess(companyId, stageId, question, memberId, assignmentRequired);
        if (session != null && expectedVersion == null) {
            throw conflict("ANSWER_VERSION_REQUIRED", "Send the displayed answer version.");
        }
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
            return interviews.deleteQuestion(companyId, stageId, questionId);
        }
        InterviewSession session = writeAccess(companyId, stageId, question, memberId, assignmentRequired);
        if (session != null && answeredTree(question, card(companyId, stageId, question.getApplicationId()))) {
            throw conflict("QUESTION_ANSWERED", "Recorded answers cannot be removed in interviewer mode.");
        }
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
        return new InterviewerWorkspace(toAssignment(session), role, session.memo(role), questions,
                view.previous(), view.schedule());
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
            List<InterviewerQuestionAccess> questions,
            List<InterviewView.PreviousInterview> previous,
            @Schema(nullable = true) InterviewView.Schedule schedule) {
    }

    public record AssignedInterview(UUID stageId, UUID applicationId, String recruitmentTitle, String stageName,
            String applicantName, @Schema(nullable = true) InterviewView.Schedule schedule,
            InterviewerRole myRole, InterviewSessionStatus status) {
    }

    public record AssignedInterviews(List<AssignedInterview> items, long total, int page, int size) {
    }
}
