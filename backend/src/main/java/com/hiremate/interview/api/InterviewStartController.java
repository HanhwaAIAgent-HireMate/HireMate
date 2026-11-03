package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewNotices;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** HR 알림: 시작한 면접, 끝난 면접, 면접관 의견이 모두 들어온 면접. */
@RestController
public class InterviewStartController {

    private final InterviewNotices notices;

    public InterviewStartController(InterviewNotices notices) {
        this.notices = notices;
    }

    @GetMapping("/api/companies/current/interviews/notices")
    public List<InterviewNotices.InterviewNotice> interviewNotices(AuthenticatedMember member) {
        return notices.recent(member.companyId());
    }
}
