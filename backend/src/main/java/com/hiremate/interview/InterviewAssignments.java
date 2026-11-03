package com.hiremate.interview;

import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewAttendanceRepository;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.interview.domain.InterviewStageAssignment;
import com.hiremate.interview.domain.InterviewStageAssignmentRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageCandidatesStarted;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접관은 면접 전형에서 한 번 배정하며 모든 지원자의 면접이 같은 배정을 사용한다. 면접이 시작된 뒤에 바꾸면 아직 시작하지 않은
 * 시간의 면접에만 적용한다. 이미 시작했거나 끝난 시간의 면접은 그 시간을 맡은 면접관과 기록을 그대로 둔다.
 */
@Service
public class InterviewAssignments {

    private final InterviewStageAssignmentRepository assignments;
    private final InterviewSessionRepository sessions;
    private final InterviewAttendanceRepository attendance;
    private final InterviewGroups groups;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationEventPublisher events;

    public InterviewAssignments(InterviewStageAssignmentRepository assignments, InterviewSessionRepository sessions,
            InterviewAttendanceRepository attendance, InterviewGroups groups, RecruitService recruits,
            ScreeningService screening, ApplicationEventPublisher events) {
        this.assignments = assignments;
        this.sessions = sessions;
        this.attendance = attendance;
        this.groups = groups;
        this.recruits = recruits;
        this.screening = screening;
        this.events = events;
    }

    /**
     * 전형의 공통 면접관. locked면 바꿀 수 없다 (결과를 확정했거나 모든 면접이 시작됐다). started는 면접 시간이 시작돼
     * 배정을 바꿔도 원래 면접관이 그대로 맡는 지원자 수다.
     */
    public record StageInterviewAssignment(UUID stageId, UUID hrMemberId, UUID practicalMemberId,
            long version, boolean locked, int started) {
    }

    @Transactional(readOnly = true)
    public StageInterviewAssignment view(UUID companyId, UUID stageId) {
        StageInfo stage = stage(companyId, stageId);
        InterviewStageAssignment assignment = assignments.findByStageIdAndCompanyId(stageId, companyId)
                .orElseThrow(() -> {
                    boolean legacy = !sessions.findByStageIdAndCompanyId(stageId, companyId).isEmpty();
                    return new ApiException(legacy ? HttpStatus.CONFLICT : HttpStatus.NOT_FOUND,
                            legacy ? "INTERVIEW_ASSIGNMENT_CONFLICT" : "INTERVIEW_ASSIGNMENT_NOT_FOUND",
                            legacy ? "Existing candidate assignments disagree. Review the stage assignment."
                                    : "Assign interviewers to this stage first.");
                });
        return toView(assignment, stage, companyId);
    }

    /** 인증 진입 계층이 두 면접관 계정의 기업과 역할을 검증한 뒤 호출한다. */
    @Transactional
    public StageInterviewAssignment assign(UUID companyId, UUID stageId, UUID hrMemberId,
            UUID practicalMemberId, Long expectedVersion) {
        recruits.lockStage(companyId, stageId);
        StageInfo stage = stage(companyId, stageId);
        if (stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE) {
            throw conflict("STAGE_CLOSED", "The interview stage is closed.");
        }
        if (hrMemberId.equals(practicalMemberId)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "DISTINCT_INTERVIEWERS", "Assign two different members.");
        }
        InterviewStageAssignment assignment = assignments.findByStageIdAndCompanyId(stageId, companyId)
                .orElse(null);
        List<InterviewSession> existing = sessions.findByStageIdAndCompanyId(stageId, companyId);
        List<InterviewSession> open = notStarted(companyId, stageId, existing);
        if (!existing.isEmpty() && open.isEmpty()) {
            throw conflict("INTERVIEW_STARTED", "Every interview has started, so no assignment can change.");
        }
        if (assignment == null) {
            if (expectedVersion != null) {
                throw conflict("SESSION_CONFLICT", "Reload the latest stage interview assignment.");
            }
            assignment = new InterviewStageAssignment(companyId, stageId, hrMemberId, practicalMemberId);
        } else {
            if (expectedVersion == null || expectedVersion != assignment.getVersion()) {
                throw conflict("SESSION_CONFLICT", "Reload the latest stage interview assignment.");
            }
            assignment.assign(hrMemberId, practicalMemberId);
        }
        assignment = assignments.saveAndFlush(assignment);
        open.forEach(session -> reassign(session, hrMemberId, practicalMemberId));
        apply(assignment, screening.applicationIds(companyId, stageId));
        return toView(assignment, stage, companyId);
    }

    /** 지원자가 나중에 들어오는 전형도 이미 저장한 공통 면접관을 자동으로 적용한다. */
    @EventListener
    @Transactional
    public void on(StageCandidatesStarted event) {
        recruits.lockStage(event.companyId(), event.stageId());
        assignments.findByStageIdAndCompanyId(event.stageId(), event.companyId())
                .ifPresent(assignment -> apply(assignment, event.applicationIds()));
    }

    private void apply(InterviewStageAssignment assignment, List<UUID> applicationIds) {
        UUID companyId = assignment.getCompanyId();
        UUID stageId = assignment.getStageId();
        Map<UUID, InterviewSession> found = sessions.findByStageIdAndCompanyId(stageId, companyId).stream()
                .collect(Collectors.toMap(InterviewSession::getApplicationId, Function.identity(),
                        (first, second) -> first, LinkedHashMap::new));
        // 전형 시작 알림을 다시 받아도 이미 만든 면접의 담당과 기록은 덮어쓰지 않는다.
        for (UUID applicationId : applicationIds) {
            if (!found.containsKey(applicationId)) {
                sessions.save(new InterviewSession(companyId, stageId, applicationId,
                        assignment.getHrMemberId(), assignment.getPracticalMemberId()));
            }
        }
        sessions.flush();
        events.publishEvent(new InterviewSessionChanged(companyId, stageId, null));
    }

    /**
     * 면접관이 바뀐 담당의 준비 완료와 개인 메모를 지운다. 준비 완료와 메모는 그 담당을 맡던 사람의 것이라 새 면접관에게
     * 넘기지 않는다. 질문과 담당(인사 · 실무)은 그대로 둔다.
     */
    private void reassign(InterviewSession session, UUID hrMemberId, UUID practicalMemberId) {
        boolean hrChanged = !session.getHrMemberId().equals(hrMemberId);
        boolean practicalChanged = !session.getPracticalMemberId().equals(practicalMemberId);
        if (!hrChanged && !practicalChanged) {
            return;
        }
        if (hrChanged && !session.memo(InterviewerRole.HR).isEmpty()) {
            session.memo(InterviewerRole.HR, "");
        }
        if (practicalChanged && !session.memo(InterviewerRole.PRACTICAL).isEmpty()) {
            session.memo(InterviewerRole.PRACTICAL, "");
        }
        session.assign(hrMemberId, practicalMemberId);
        attendance.clear(session.getStageId(), session.getApplicationId());
    }

    /**
     * 아직 시작하지 않은 시간의 면접 (일정 미정 포함). 같은 시간 면접자는 함께 시작하므로 시간 단위로 본다. 시작한 시간에서
     * 불참으로 빠진 지원자도 그 시간 면접관에게 남긴다 (불참을 취소하면 그 면접에 다시 들어간다).
     */
    private List<InterviewSession> notStarted(UUID companyId, UUID stageId, List<InterviewSession> all) {
        Map<UUID, List<InterviewSession>> slots = InterviewGroups.byApplication(all,
                groups.stageSchedule(companyId, stageId));
        return all.stream().filter(session -> {
            InterviewSessionStatus slot = InterviewGroups.status(slots.get(session.getApplicationId()));
            return slot == InterviewSessionStatus.SCHEDULED || slot == InterviewSessionStatus.ABSENT;
        }).toList();
    }

    private StageInfo stage(UUID companyId, UUID stageId) {
        StageInfo stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (stage.type() != StageType.INTERVIEW) {
            throw conflict("NOT_INTERVIEW_STAGE", "Only interview stages have interviewer assignments.");
        }
        return stage;
    }

    private StageInterviewAssignment toView(InterviewStageAssignment assignment, StageInfo stage, UUID companyId) {
        List<InterviewSession> all = sessions.findByStageIdAndCompanyId(stage.id(), companyId);
        int started = all.size() - notStarted(companyId, stage.id(), all).size();
        boolean closed = stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE;
        return new StageInterviewAssignment(assignment.getStageId(), assignment.getHrMemberId(),
                assignment.getPracticalMemberId(), assignment.getVersion(),
                closed || (!all.isEmpty() && started == all.size()), started);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }
}
