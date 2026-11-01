package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.AssignedStage;
import com.hiremate.interview.InterviewAssignments;
import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.StageInterviewers;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 면접관 지정과 면접관의 "내 면접" 목록. 지정 저장은 HR만, 조회는 지정된 면접관도 쓴다. */
@RestController
public class InterviewerController {

    private final InterviewAssignments assignments;

    public InterviewerController(InterviewAssignments assignments) {
        this.assignments = assignments;
    }

    @GetMapping("/api/stages/{stageId}/interviewers")
    public StageInterviewers interviewers(AuthenticatedMember member, @PathVariable UUID stageId) {
        return assignments.interviewers(member.companyId(), stageId);
    }

    /** 담당별 면접관을 통째로 바꾼다. 비운 담당은 지정이 풀린다. */
    @PutMapping("/api/stages/{stageId}/interviewers")
    public StageInterviewers assign(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody AssignRequest request) {
        return assignments.assign(member.companyId(), stageId, member.memberId(), request.slots().stream()
                .map(slot -> new StageInterviewers.Slot(slot.role(), slot.memberId(), "")).toList());
    }

    /** 로그인한 계정이 지정된 면접 전형. HR 계정도 면접관으로 지정되면 여기에 보인다. */
    @GetMapping("/api/interviewer/stages")
    public List<AssignedStage> myStages(AuthenticatedMember member) {
        return assignments.stages(member.companyId(), member.memberId());
    }

    public record AssignRequest(@NotNull @Size(max = 10) List<@Valid @NotNull SlotRequest> slots) {
    }

    public record SlotRequest(@NotNull InterviewerRole role, @NotNull UUID memberId) {
    }
}
