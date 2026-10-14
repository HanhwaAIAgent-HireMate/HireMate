package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.ApplicationSubmitted;
import com.hiremate.posting.PostingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

/** 지원서가 접수되면 Application Agent로 분석해 둔다. 질문할 때마다 원문을 다시 읽지 않기 위해서다. */
@Component
class ApplicationAnalysisListener {

    private static final Logger log = LoggerFactory.getLogger(ApplicationAnalysisListener.class);

    private final ApplicationService applications;
    private final PostingService postings;
    private final ApplicationAgent agent;

    ApplicationAnalysisListener(ApplicationService applications, PostingService postings, ApplicationAgent agent) {
        this.applications = applications;
        this.postings = postings;
        this.agent = agent;
    }

    @ApplicationModuleListener
    void on(ApplicationSubmitted event) {
        try {
            ApplicantDetail applicant = applications.detailForAnalysis(event.applicationId());
            applications.recordAnalysis(event.applicationId(), agent.analyze(applicant,
                    postings.draftContext(event.companyId(), event.recruitmentId()).content()));
        } catch (RuntimeException exception) {
            log.warn("Application analysis failed for {}", event.applicationId(), exception);
            applications.markAnalysisFailed(event.applicationId());
        }
    }
}
