package com.hiremate.report;

import com.hiremate.global.ApiException;
import com.hiremate.global.JsonText;
import com.hiremate.recruit.RecruitService;
import com.hiremate.report.domain.Report;
import com.hiremate.report.domain.ReportRepository;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 최종 채용 리포트 저장과 조회. 리포트는 채용을 종료할 때 Report Agent가 한 번 쓴다. */
@Service
public class ReportService {

    private final ReportRepository reports;
    private final RecruitService recruits;

    public ReportService(ReportRepository reports, RecruitService recruits) {
        this.reports = reports;
        this.recruits = recruits;
    }

    @Transactional
    public void save(UUID companyId, UUID recruitmentId, ReportContent content, String agent) {
        if (!reports.existsByRecruitmentId(recruitmentId)) {
            reports.save(new Report(recruitmentId, companyId, JsonText.write(content), agent));
        }
    }

    /** 아직 쓰는 중이면 404 REPORT_NOT_READY다. */
    @Transactional(readOnly = true)
    public ReportView view(UUID companyId, UUID recruitmentId) {
        String title = recruits.get(companyId, recruitmentId).title();
        Report report = reports.findByRecruitmentIdAndCompanyId(recruitmentId, companyId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "REPORT_NOT_READY", "The report is not ready."));
        return new ReportView(recruitmentId, title, report.getGeneratedAt(), report.getAgent(),
                JsonText.read(report.getContent(), ReportContent.class));
    }
}
