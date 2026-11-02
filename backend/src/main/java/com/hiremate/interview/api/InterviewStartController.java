package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewSessions;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** HR 알림: 면접관이 모두 준비 완료해 시작한 면접. */
@RestController
public class InterviewStartController {

    private final InterviewSessions sessions;

    public InterviewStartController(InterviewSessions sessions) {
        this.sessions = sessions;
    }

    @GetMapping("/api/companies/current/interviews/started")
    public List<InterviewSessions.StartedInterview> startedInterviews(AuthenticatedMember member) {
        return sessions.recentStarts(member.companyId());
    }
}
