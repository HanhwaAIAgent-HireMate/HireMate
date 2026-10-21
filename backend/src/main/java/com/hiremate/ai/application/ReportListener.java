package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentClosed;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.report.ReportContent;
import com.hiremate.report.ReportService;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageCandidateView;
import com.hiremate.screening.StageOverview;
import com.hiremate.screening.StageResults;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 채용을 종료하면 Report Agent가 최종 리포트를 쓴다. 리포트는 채용 상태를 바꾸지 않는다. */
@Component
class ReportListener {

    private final RecruitService recruits;
    private final ScreeningService screening;
    private final ApplicationService applications;
    private final PostingService postings;
    private final CandidateAnalyst analyst;
    private final ReportAgent agent;
    private final ReportService reports;
    private final AiSettings settings;

    ReportListener(RecruitService recruits, ScreeningService screening, ApplicationService applications,
            PostingService postings, CandidateAnalyst analyst, ReportAgent agent, ReportService reports,
            AiSettings settings) {
        this.recruits = recruits;
        this.screening = screening;
        this.applications = applications;
        this.postings = postings;
        this.analyst = analyst;
        this.agent = agent;
        this.reports = reports;
        this.settings = settings;
    }

    @ApplicationModuleListener
    void on(RecruitmentClosed event) {
        UUID companyId = event.companyId();
        RecruitmentInfo recruitment = recruits.get(companyId, event.recruitmentId());
        Map<UUID, StageOverview.DecisionCounts> counts = screening.stageCounts(companyId, recruitment.id());
        List<ReportContent.ReportStage> stages = recruitment.stages().stream()
                .filter(stage -> counts.containsKey(stage.id()))
                .map(stage -> new ReportContent.ReportStage(stage.name(), counts.get(stage.id()).total(),
                        counts.get(stage.id()).pass(), counts.get(stage.id()).fail()))
                .toList();
        StageInfo last = recruitment.stages().getLast();
        StageResults results = screening.results(companyId, last.id());
        var posting = postings.draftContext(companyId, recruitment.id()).content();
        var rubric = postings.screeningRubric(companyId, recruitment.id());
        List<ReportInput.FinalistInput> finalists = applications.applicants(companyId, results.passed()).stream()
                .map(applicant -> finalist(companyId, applicant, posting, rubric))
                .toList();
        List<Long> undecided = recruitment.stages().stream()
                .filter(stage -> counts.containsKey(stage.id()))
                .map(stage -> screening.results(companyId, stage.id()).undecidedAtConfirm())
                .toList();
        ReportContent content = agent.write(new ReportInput(recruitment.title(),
                applications.count(companyId, recruitment.id()), stages, finalists, undecided));
        reports.save(companyId, recruitment.id(), content,
                settings.isStub(AiAgent.REPORT) ? "Report Agent · 개발용" : "Report Agent");
    }

    private ReportInput.FinalistInput finalist(UUID companyId, ApplicantInfo applicant,
            com.hiremate.posting.PostingContent posting, com.hiremate.posting.ScreeningRubric rubric) {
        CandidateAnalysis analysis = analyst.analyze(applications.detail(companyId, applicant.applicationId()),
                posting, rubric);
        List<String> memos = screening.history(companyId, applicant.applicationId()).stream()
                .map(StageCandidateView::memo)
                .filter(memo -> !memo.isBlank())
                .toList();
        return new ReportInput.FinalistInput(applicant.name(), analysis.notable(), memos);
    }
}
