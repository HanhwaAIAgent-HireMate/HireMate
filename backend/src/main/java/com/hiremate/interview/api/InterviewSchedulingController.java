package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewScheduling;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** HR이 확정한 전형의 다음 면접 일정 상태와 재시도. */
@RestController
@RequestMapping("/api/stages/{stageId}/interview-scheduling")
public class InterviewSchedulingController {

    private final InterviewScheduling scheduling;

    public InterviewSchedulingController(InterviewScheduling scheduling) {
        this.scheduling = scheduling;
    }

    @GetMapping
    public InterviewScheduling.Status status(AuthenticatedMember member, @PathVariable UUID stageId) {
        return scheduling.status(member.companyId(), stageId);
    }

    @PostMapping("/retry")
    public InterviewScheduling.Status retry(AuthenticatedMember member, @PathVariable UUID stageId) {
        return scheduling.request(member.companyId(), stageId);
    }
}
