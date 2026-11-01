package com.hiremate.interview;

import com.hiremate.activity.ActivityService;
import com.hiremate.global.ApiException;
import com.hiremate.global.CompanyMember;
import com.hiremate.global.MemberDirectory;
import com.hiremate.interview.domain.InterviewAssignment;
import com.hiremate.interview.domain.InterviewAssignmentRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 면접 전형마다 지정한 면접관 계정. "이 계정이 이 전형 · 담당에 지정됐나"는 여기서만 판단한다.
 *
 * <p>지정은 (전형, 담당, 계정) 행이다. 지금 화면은 담당마다 한 명을 고르지만, 담당별 인원이나 담당 종류를 바꿔도
 * 이 클래스 밖의 코드는 지정 인원을 가정하지 않는다.
 */
@Service
public class InterviewAssignments {

    private final InterviewAssignmentRepository assignments;
    private final RecruitService recruits;
    private final ScreeningService screening;
    private final MemberDirectory members;
    private final ActivityService activity;

    public InterviewAssignments(InterviewAssignmentRepository assignments, RecruitService recruits,
            ScreeningService screening, MemberDirectory members, ActivityService activity) {
        this.assignments = assignments;
        this.recruits = recruits;
        this.screening = screening;
        this.members = members;
        this.activity = activity;
    }

    @Transactional(readOnly = true)
    public StageInterviewers interviewers(UUID companyId, UUID stageId) {
        interviewStage(companyId, stageId);
        Map<UUID, String> names = members.members(companyId).stream()
                .collect(Collectors.toMap(CompanyMember::memberId, CompanyMember::name));
        return new StageInterviewers(assignments.findByStageIdAndCompanyId(stageId, companyId).stream()
                .sorted(Comparator.comparing(InterviewAssignment::getInterviewerRole)
                        .thenComparing(InterviewAssignment::getAssignedAt))
                .map(slot -> new StageInterviewers.Slot(slot.getInterviewerRole(), slot.getMemberId(),
                        names.getOrDefault(slot.getMemberId(), "")))
                .toList());
    }

    /** 전형의 지정을 통째로 바꾼다. slots에 없는 담당은 지정이 풀린다. 결과를 확정한 전형은 바꿀 수 없다. */
    @Transactional
    public StageInterviewers assign(UUID companyId, UUID stageId, UUID actorId,
            List<StageInterviewers.Slot> slots) {
        StageInfo stage = interviewStage(companyId, stageId);
        if (stage.status() != StageStatus.PENDING && stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_CLOSED",
                    "Interviewers can only be assigned before or during the interview.");
        }
        Map<String, StageInterviewers.Slot> unique = new LinkedHashMap<>();
        for (StageInterviewers.Slot slot : slots) {
            if (members.find(companyId, slot.memberId()).isEmpty()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "MEMBER_NOT_FOUND", "Member not found.");
            }
            unique.putIfAbsent(slot.role() + ":" + slot.memberId(), slot);
        }
        assignments.deleteByStageIdAndCompanyId(stageId, companyId);
        assignments.flush();
        unique.values().forEach(slot -> assignments.save(
                new InterviewAssignment(stageId, slot.role(), slot.memberId(), companyId)));
        activity.record(companyId, actorId, "ASSIGN_INTERVIEWERS", "STAGE", stageId, unique.values().stream()
                .map(slot -> slot.role() + "=" + slot.memberId()).collect(Collectors.joining(",")));
        return interviewers(companyId, stageId);
    }

    /** 계정이 이 전형에서 맡은 담당. 지정되지 않았으면 비어 있다. */
    @Transactional(readOnly = true)
    public Set<InterviewerRole> roles(UUID companyId, UUID memberId, UUID stageId) {
        Set<InterviewerRole> roles = EnumSet.noneOf(InterviewerRole.class);
        assignments.findByMemberIdAndStageIdAndCompanyId(memberId, stageId, companyId)
                .forEach(slot -> roles.add(slot.getInterviewerRole()));
        return roles;
    }

    @Transactional(readOnly = true)
    public boolean assigned(UUID companyId, UUID memberId, UUID stageId) {
        return !assignments.findByMemberIdAndStageIdAndCompanyId(memberId, stageId, companyId).isEmpty();
    }

    /** 채용의 면접 전형 중 하나라도 지정됐나. 지원 문서처럼 채용 단위 경로를 열 때 쓴다. */
    @Transactional(readOnly = true)
    public boolean assignedInRecruitment(UUID companyId, UUID memberId, UUID recruitmentId) {
        Set<UUID> stages = assignments.findByMemberIdAndCompanyId(memberId, companyId).stream()
                .map(InterviewAssignment::getStageId).collect(Collectors.toSet());
        if (stages.isEmpty()) {
            return false;
        }
        return recruits.list(companyId).stream().filter(recruitment -> recruitment.id().equals(recruitmentId))
                .flatMap(recruitment -> recruitment.stages().stream()).anyMatch(stage -> stages.contains(stage.id()));
    }

    /** 내가 지정된 면접 전형. 채용을 만든 순서, 전형 순서다. */
    @Transactional(readOnly = true)
    public List<AssignedStage> stages(UUID companyId, UUID memberId) {
        Map<UUID, List<InterviewerRole>> roles = assignments.findByMemberIdAndCompanyId(memberId, companyId).stream()
                .collect(Collectors.groupingBy(InterviewAssignment::getStageId,
                        Collectors.mapping(InterviewAssignment::getInterviewerRole, Collectors.toList())));
        if (roles.isEmpty()) {
            return List.of();
        }
        return recruits.list(companyId).stream()
                .flatMap(recruitment -> recruitment.stages().stream().filter(stage -> roles.containsKey(stage.id()))
                        .map(stage -> assignedStage(companyId, recruitment, stage,
                                roles.get(stage.id()).stream().sorted().toList())))
                .toList();
    }

    private AssignedStage assignedStage(UUID companyId, RecruitmentInfo recruitment, StageInfo stage,
            List<InterviewerRole> roles) {
        long count = stage.status() == StageStatus.PENDING ? 0
                : screening.overview(companyId, stage.id()).counts().total();
        return new AssignedStage(stage.id(), stage.name(), stage.status(), recruitment.id(), recruitment.title(),
                roles, count);
    }

    private StageInfo interviewStage(UUID companyId, UUID stageId) {
        StageInfo stage = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow();
        if (stage.type() != StageType.INTERVIEW) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_INTERVIEW_STAGE", "Only interview stages have interviewers.");
        }
        return stage;
    }
}
