package com.hiremate.report.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.report.ReportService;
import com.hiremate.report.ReportView;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** 최종 채용 리포트 (RPT-01). */
@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/recruitments/{recruitmentId}/report")
    public ReportView report(AuthenticatedMember member, @PathVariable UUID recruitmentId) {
        return reports.view(member.companyId(), recruitmentId);
    }
}
