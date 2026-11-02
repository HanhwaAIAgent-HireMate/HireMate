package com.hiremate.interview;

import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewQuestionRepository;
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

/** 면접관은 면접 전형에서 한 번 배정하며 모든 지원자의 면접이 같은 배정을 사용한다. */
@Service
public class InterviewAssignments {

    private final InterviewStageAssignmentRepository assignments;
    private final InterviewSessionRepository sessions;
    private final InterviewQuestionRepository questions;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationEventPublisher events;

    public InterviewAssignments(InterviewStageAssignmentRepository assignments, InterviewSessionRepository sessions,
            InterviewQuestionRepository questions, RecruitService recruits, ScreeningService screening,
            ApplicationEventPublisher events) {
        this.assignments = assignments;
        this.sessions = sessions;
        this.questions = questions;
        this.recruits = recruits;
        this.screening = screening;
        this.events = events;
    }

    public record StageInterviewAssignment(UUID stageId, UUID hrMemberId, UUID practicalMemberId,
            long version, boolean locked) {
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
        return toView(assignment, locked(companyId, stageId, stage));
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
        if ((assignment != null || !existing.isEmpty()) && locked(companyId, stageId, stage)) {
            throw conflict("INTERVIEW_STARTED", "Assignments are locked after any interview recording starts.");
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
        InterviewStageAssignment saved = assignment;
        existing.forEach(session -> session.assign(saved.getHrMemberId(), saved.getPracticalMemberId()));
        apply(assignment, screening.applicationIds(companyId, stageId));
        return toView(assignment, locked(companyId, stageId, stage));
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

    private boolean locked(UUID companyId, UUID stageId, StageInfo stage) {
        if (stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE) {
            return true;
        }
        boolean recorded = sessions.findByStageIdAndCompanyId(stageId, companyId).stream()
                // 불참은 면접을 하지 않은 것이라 배정을 잠그지 않는다
                .anyMatch(session -> session.getStatus() == InterviewSessionStatus.IN_PROGRESS
                        || session.getStatus() == InterviewSessionStatus.ENDED
                        || !session.getHrMemo().isBlank() || !session.getPracticalMemo().isBlank());
        return recorded || questions.findByStageIdAndCompanyId(stageId, companyId).stream()
                .anyMatch(question -> !question.getAnswer().isBlank());
    }

    private StageInfo stage(UUID companyId, UUID stageId) {
        StageInfo stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (stage.type() != StageType.INTERVIEW) {
            throw conflict("NOT_INTERVIEW_STAGE", "Only interview stages have interviewer assignments.");
        }
        return stage;
    }

    private static StageInterviewAssignment toView(InterviewStageAssignment assignment, boolean locked) {
        return new StageInterviewAssignment(assignment.getStageId(), assignment.getHrMemberId(),
                assignment.getPracticalMemberId(), assignment.getVersion(), locked);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }
}
