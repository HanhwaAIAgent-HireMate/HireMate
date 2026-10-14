package com.hiremate.dashboard.api;

import com.hiremate.dashboard.application.DashboardService;
import com.hiremate.dashboard.application.DashboardView;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.recruit.RecruitmentStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 채용 대시보드. 로고를 누르면 가는 첫 화면이다. */
@RestController
public class DashboardController {

    private final DashboardService dashboard;

    public DashboardController(DashboardService dashboard) {
        this.dashboard = dashboard;
    }

    @GetMapping("/api/recruitments")
    public DashboardView recruitments(AuthenticatedMember member,
            @RequestParam(required = false) RecruitmentStatus status, @RequestParam(required = false) String query) {
        return dashboard.dashboard(member.companyId(), status, query);
    }
}
