package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationAnalysisRequested;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.job.JobQueue;
import com.hiremate.posting.PostingService;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 지원서가 접수되거나 담당자가 다시 분석을 요청하면 Application Agent에 분석을 맡긴다. 질문할 때마다 원문을 다시 읽지 않기
 * 위해서다. remote면 분석 작업을 대기열에 넣고 결과는 {@link ApplicationAnalysisResults}가 기록한다. 맡기지 못하면 분석
 * 실패로 두어 담당자가 다시 요청할 수 있게 한다 (NFR-05).
 */
@Component
class ApplicationAnalysisListener {

    private static final Logger log = LoggerFactory.getLogger(ApplicationAnalysisListener.class);

    private final ApplicationService applications;
    private final PostingService postings;
    private final ApplicationAgent agent;
    private final JobQueue jobs;
    private final AiSettings settings;
    private final Duration recoverAfter;

    ApplicationAnalysisListener(ApplicationService applications, PostingService postings, ApplicationAgent agent,
            JobQueue jobs, AiSettings settings, @Value("${hiremate.jobs.recover-after}") Duration recoverAfter) {
        this.applications = applications;
        this.postings = postings;
        this.agent = agent;
        this.jobs = jobs;
        this.settings = settings;
        this.recoverAfter = recoverAfter;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        analyze(event.applicationId(), event.companyId(), event.recruitmentId());
    }

    @ApplicationModuleListener
    void on(ApplicationAnalysisRequested event) {
        analyze(event.applicationId(), event.companyId(), event.recruitmentId());
    }

    /**
     * 분석 중인데 대기열에 작업이 없는 지원서를 다시 맡긴다. Redis를 비웠거나 작업을 넣기 전에 서버가 멈춘 경우다.
     * stub은 대기열을 쓰지 않아 하지 않는다.
     */
    @Scheduled(fixedDelayString = "${hiremate.jobs.retry-interval}")
    void recover() {
        if (settings.isStub(AiAgent.APPLICATION)) {
            return;
        }
        try {
            Instant submittedBefore = Instant.now().minus(recoverAfter);
            for (ApplicationAnalysisRequested pending : applications.pendingAnalyses(submittedBefore)) {
                if (!jobs.isOpen(ApplicationAgent.ANALYZE_JOB, pending.applicationId().toString())) {
                    log.info("Analysis job for {} was lost and is queued again", pending.applicationId());
                    analyze(pending.applicationId(), pending.companyId(), pending.recruitmentId());
                }
            }
        } catch (RuntimeException exception) {
            log.warn("Lost analysis jobs could not be checked: {}", exception.getMessage());
        }
    }

    private void analyze(UUID applicationId, UUID companyId, UUID recruitmentId) {
        try {
            ApplicantDetail applicant = applications.detailForAnalysis(applicationId);
            agent.analyze(applicant, postings.draftContext(companyId, recruitmentId).content(),
                    postings.screeningRubric(companyId, recruitmentId))
                    .ifPresent(analysis -> applications.recordAnalysis(applicationId, analysis));
        } catch (RuntimeException exception) {
            log.warn("Application analysis failed for {}", applicationId, exception);
            applications.markAnalysisFailed(applicationId);
        }
    }
}
