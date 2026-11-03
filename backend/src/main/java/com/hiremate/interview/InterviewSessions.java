package com.hiremate.interview;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
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
    private final InterviewGroups groups;
    private final InterviewAttendanceRepository attendance;
    private final ApplicationEventPublisher events;

    public InterviewSessions(InterviewSessionRepository sessions, InterviewQuestionRepository questions,
            InterviewService interviews, RecruitService recruits, ApplicationService applications,
            InterviewAttendances attendances, InterviewGroups groups, InterviewAttendanceRepository attendance,
            ApplicationEventPublisher events) {
        this.attendances = attendances;
        this.groups = groups;
        this.attendance = attendance;
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
     * 면접관의 [준비 완료]. 면접은 같은 시간 면접자 묶음 단위로 연다. 그 시간 면접자(불참 제외) 모두에 대해 준비로 세고,
     * 배정된 두 면접관이 모두 준비 완료하고 접속 중이면 그 시간 면접자를 한꺼번에 시작한다.
     * 일정이 없거나, 질문이 시작할 수 있는 상태가 아닌 지원자가 있으면 준비 완료를 받지 않는다.
     */
    @Transactional
    public InterviewAttendances.Attendance ready(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        requireActive(companyId, stageId);
        if (groups.scheduledAt(stageId, applicationId) == null) {
            throw conflict("INTERVIEW_NOT_SCHEDULED", "Set the interview time first.");
        }
        List<InterviewSession> members = groups.members(session);
        List<InterviewSession> present = InterviewGroups.present(members);
        if (InterviewGroups.status(members) == InterviewSessionStatus.SCHEDULED) {
            for (InterviewSession member : present) {
                StartProblem problem = startProblem(companyId, stageId, member.getApplicationId());
                if (problem != null) {
                    throw conflict(problem.code(), problem.message());
                }
            }
            attendances.markReady(present, memberId);
            if (attendances.ready(session, members)) {
                Instant now = Instant.now();
                present.forEach(member -> member.start(now));
                sessions.flush();
            }
            members.forEach(member -> changed(companyId, stageId, member.getApplicationId()));
        }
        return attendances.attendance(companyId, stageId, applicationId, memberId);
    }

    /** 시작 전에 [준비 완료]를 거둔다. 그 시간 면접자 모두에 대해 거두고, 시작한 면접은 그대로 둔다. */
    @Transactional
    public InterviewAttendances.Attendance cancelReady(UUID companyId, UUID stageId, UUID applicationId,
            UUID memberId) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        List<InterviewSession> members = groups.members(session);
        if (InterviewGroups.status(members) == InterviewSessionStatus.SCHEDULED) {
            attendances.clearReady(members, memberId);
            members.forEach(member -> changed(companyId, stageId, member.getApplicationId()));
        }
        return attendances.attendance(companyId, stageId, applicationId, memberId);
    }

    /**
     * 면접 시간에 오지 않은 지원자를 불참으로 두거나 되돌린다. 불참한 지원자는 같은 시간 면접의 준비 · 시작 · 종료에서 빠진다.
     * 답변을 기록한 지원자는 불참으로 둘 수 없고, 끝난 면접의 불참은 되돌릴 수 없다.
     */
    @Transactional
    public InterviewerWorkspace absent(UUID companyId, UUID stageId, UUID applicationId, UUID memberId,
            boolean absent) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        requireAssigned(session, memberId);
        requireActive(companyId, stageId);
        List<InterviewSession> members = groups.members(session);
        if (absent && session.getStatus() != InterviewSessionStatus.ABSENT) {
            if (session.getStatus() == InterviewSessionStatus.ENDED) {
                throw conflict("INTERVIEW_ENDED", "The interview has ended.");
            }
            if (card(companyId, stageId, applicationId).stream().anyMatch(q -> !q.getAnswer().isBlank())) {
                throw conflict("INTERVIEW_ANSWERED", "Applicants with recorded answers cannot be marked absent.");
            }
            session.markAbsent();
            attendance.clear(stageId, applicationId);
        } else if (!absent && session.getStatus() == InterviewSessionStatus.ABSENT) {
            List<InterviewSession> others = members.stream().filter(member -> member != session).toList();
            InterviewSessionStatus back = InterviewGroups.status(others);
            if (back == InterviewSessionStatus.ENDED) {
                throw conflict("INTERVIEW_ENDED", "The interview has ended.");
            }
            session.rejoin(back == InterviewSessionStatus.IN_PROGRESS ? back : InterviewSessionStatus.SCHEDULED,
                    InterviewGroups.startedAt(others));
            // 다시 들어온 지원자에 대해서는 아무도 준비하지 않았으니 시작 전이면 준비를 처음부터 받는다
            if (back != InterviewSessionStatus.IN_PROGRESS) {
                members.forEach(member -> attendance.clear(stageId, member.getApplicationId()));
            }
        }
        sessions.flush();
        members.forEach(member -> changed(companyId, stageId, member.getApplicationId()));
        return workspace(session, memberId);
    }

    /** 면접을 시작할 수 없게 막는 질문 구성. code · message는 API 오류, label은 면접관 화면에 보이는 말이다 */
    private record StartProblem(String code, String message, String label) {
    }

    /** 면접을 시작할 수 있는 질문 구성인가: 생성이 끝났고, 모든 질문에 담당이 있고, 담당 규칙을 지킨다. */
    private StartProblem startProblem(UUID companyId, UUID stageId, UUID applicationId) {
        if (interviews.preparing(companyId, stageId, applicationId)) {
            return new StartProblem("QUESTIONS_PREPARING", "Wait for question preparation to finish.",
                    "질문을 만드는 중이에요");
        }
        List<InterviewQuestion> card = card(companyId, stageId, applicationId);
        if (card.isEmpty()) {
            return new StartProblem("QUESTION_OWNER_REQUIRED", "Prepare questions before starting.", "질문이 없어요");
        }
        long unowned = card.stream().filter(question -> question.getInterviewerRole() == null).count();
        if (unowned > 0) {
            return new StartProblem("QUESTION_OWNER_REQUIRED", "Assign all question owners before starting.",
                    "담당이 없는 질문 " + unowned + "개");
        }
        for (InterviewQuestion question : card) {
            if (InterviewService.INTRO.equals(question.getText())
                    && question.getInterviewerRole() != InterviewerRole.HR) {
                return new StartProblem("INTRO_OWNER", "HR records the common introduction.",
                        "자기소개는 인사 담당이어야 해요");
            }
            if (question.getParentQuestionId() != null && card.stream().anyMatch(parent ->
                    parent.getId().equals(question.getParentQuestionId())
                            && parent.getInterviewerRole() != question.getInterviewerRole())) {
                return new StartProblem("FOLLOW_UP_OWNER", "A follow-up must keep its parent's owner.",
                        "꼬리질문 담당이 원래 질문과 달라요");
            }
        }
        return null;
    }

    /**
     * 면접관의 [면접 종료]. 같은 시간 면접자 중 진행 중인 지원자 모두에 대해 이 면접관이 마친 것으로 남기고, 두 면접관이
     * 모두 마치면 그 지원자들의 면접을 함께 끝낸다. 먼저 마친 면접관은 상대 면접관이 끝낼 때까지 기록을 고칠 수 없다.
     */
    @Transactional
    public InterviewerWorkspace end(UUID companyId, UUID stageId, UUID applicationId, UUID memberId) {
        recruits.lockStage(companyId, stageId);
        InterviewSession session = lock(companyId, stageId, applicationId);
        InterviewerRole role = requireAssigned(session, memberId);
        List<InterviewSession> members = groups.members(session);
        InterviewSessionStatus status = InterviewGroups.status(members);
        if (status == InterviewSessionStatus.SCHEDULED) {
            throw conflict("INTERVIEW_NOT_STARTED", "Start the interview first.");
        }
        if (status == InterviewSessionStatus.IN_PROGRESS && !InterviewGroups.endedBy(members, role)) {
            requireActive(companyId, stageId);
            Instant now = Instant.now();
            List<InterviewSession> running = members.stream()
                    .filter(member -> member.getStatus() == InterviewSessionStatus.IN_PROGRESS).toList();
            running.forEach(member -> member.endBy(role, now));
            if (running.stream().allMatch(member -> member.endedBy(InterviewerRole.HR)
                    && member.endedBy(InterviewerRole.PRACTICAL))) {
                for (InterviewSession member : running) {
                    interviews.submitPendingAnswers(companyId, stageId, member.getApplicationId());
                    member.end(now);
                }
            }
            sessions.flush();
            members.forEach(member -> changed(companyId, stageId, member.getApplicationId()));
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

    /**
     * 개인 메모만 반환한다. 상대 면접관의 메모는 API에 포함하지 않는다. 나만 보는 메모라 면접 전 준비와 면접 뒤 정리에도 쓰도록
     * 진행 중인 전형이면 면접 상태와 상관없이 고칠 수 있다.
     */
    @Transactional
    public InterviewerWorkspace memo(UUID companyId, UUID stageId, UUID applicationId, UUID memberId, String memo,
            long expectedVersion) {
        InterviewSession session = lock(companyId, stageId, applicationId);
        InterviewerRole role = requireAssigned(session, memberId);
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
                requireOpen(session, actual);
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
        InterviewSession session = writeAccess(companyId, stageId, question, memberId, assignmentRequired, true);
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
        return writeAccess(companyId, stageId, question, memberId, assignmentRequired, false);
    }

    /** beforeStart면 시작 전 면접에서도 받는다 (내 담당 질문을 미리 넣고 빼기) */
    private InterviewSession writeAccess(UUID companyId, UUID stageId, InterviewQuestion question, UUID memberId,
            boolean assignmentRequired, boolean beforeStart) {
        InterviewSession session = sessions.lock(companyId, stageId, question.getApplicationId()).orElse(null);
        if (session == null) {
            if (assignmentRequired) {
                throw notFound();
            }
            return null;
        }
        InterviewerRole role = requireAssigned(session, memberId);
        if (beforeStart) {
            requireOpen(session, role);
        } else {
            requireRunning(session, role);
        }
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
                            : session.getStatus() == InterviewSessionStatus.ABSENT ? "불참"
                            : session.endedBy(role) ? "면접 종료" : null;
                    boolean canFollowUp = reason == null && !question.answer().isBlank()
                            && !hasChild(question, view.questions()) && depth(question, view.questions()) < 2;
                    // 시작 전에도 내 담당 질문은 미리 빼 둘 수 있다 (답은 면접을 시작한 뒤에 적는다)
                    boolean preparing = active && question.interviewerRole() == role
                            && session.getStatus() == InterviewSessionStatus.SCHEDULED;
                    return new InterviewerQuestionAccess(question, reason == null, canFollowUp,
                            (reason == null || preparing) && !answeredView(question, view.questions()), reason);
                }).toList();
        return new InterviewerWorkspace(toAssignment(session), role, session.memo(role), session.memoVersion(role),
                questions, view.previous(), view.schedule(), group(session));
    }

    /** 이 지원자와 같은 시간 면접자. 면접관 화면은 이것으로 함께 시작하고 끝낼 지원자와 막힌 이유를 보여 준다 */
    private InterviewGroup group(InterviewSession session) {
        UUID companyId = session.getCompanyId();
        UUID stageId = session.getStageId();
        List<InterviewSession> members = groups.members(session);
        Map<UUID, String> names = applications.applicants(companyId,
                members.stream().map(InterviewSession::getApplicationId).toList()).stream()
                .collect(Collectors.toMap(ApplicantInfo::applicationId, ApplicantInfo::name));
        return new InterviewGroup(groups.scheduledAt(stageId, session.getApplicationId()),
                InterviewGroups.status(members), members.stream().map(member -> {
                    UUID id = member.getApplicationId();
                    StartProblem problem = member.getStatus() == InterviewSessionStatus.SCHEDULED
                            ? startProblem(companyId, stageId, id) : null;
                    return new GroupMember(id, names.getOrDefault(id, ""), member.getStatus(),
                            card(companyId, stageId, id).stream().anyMatch(q -> !q.getAnswer().isBlank()),
                            problem == null ? null : problem.label());
                }).toList());
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

    /** 면접이 진행 중이고 이 면접관이 아직 [면접 종료]를 누르지 않았다 */
    private static void requireRunning(InterviewSession session, InterviewerRole role) {
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS) {
            throw conflict("INTERVIEW_NOT_RUNNING", "The interview must be in progress.");
        }
        if (session.endedBy(role)) {
            throw conflict("INTERVIEWER_ENDED", "You have already ended this interview.");
        }
    }

    /** 면접을 시작하기 전이거나, 진행 중이고 이 면접관이 아직 [면접 종료]를 누르지 않았다. 불참한 지원자는 받지 않는다 */
    private static void requireOpen(InterviewSession session, InterviewerRole role) {
        if (session.getStatus() != InterviewSessionStatus.SCHEDULED) {
            requireRunning(session, role);
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
            @Schema(nullable = true) InterviewView.Schedule schedule,
            InterviewGroup group) {
    }

    /** 같은 시간 면접. 일정이 없으면 scheduledAt이 없고 지원자 한 명뿐이며 시작할 수 없다 */
    public record InterviewGroup(@Schema(nullable = true) Instant scheduledAt, InterviewSessionStatus status,
            List<GroupMember> members) {
    }

    /** 같은 시간 면접자 한 명. blocker는 면접을 시작할 수 없게 막는 이유다 (시작 전에만 있다) */
    public record GroupMember(UUID applicationId, String applicantName, InterviewSessionStatus status,
            boolean answered, @Schema(nullable = true) String blocker) {
    }

    public record AssignedInterview(UUID stageId, UUID applicationId, String recruitmentTitle, String stageName,
            String applicantName, @Schema(nullable = true) InterviewView.Schedule schedule,
            InterviewerRole myRole, InterviewSessionStatus status, UUID recruitmentId) {
    }

    public record AssignedInterviews(List<AssignedInterview> items, long total, int page, int size) {
    }
}
