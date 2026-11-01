package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.job.JobFinished;
import com.hiremate.job.JobResult;
import com.hiremate.job.JobStatus;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * AI 워커가 끝낸 지원서 분석을 기록한다. 업무 데이터는 backend만 쓴다 (아키텍처 규칙 3). 실패한 분석은 분석 실패로 두어
 * 담당자가 다시 요청할 수 있게 한다 (NFR-05). 분석을 기록한 뒤 회사 인재상도 판정해 둔다. 인재상 판정이 실패해도 분석은 그대로다.
 */
@Component
class ApplicationAnalysisResults {

    private static final Logger log = LoggerFactory.getLogger(ApplicationAnalysisResults.class);

    private final ApplicationService applications;
    private final CandidateAnalysisService candidateAnalysis;
    private final JsonMapper json;

    ApplicationAnalysisResults(ApplicationService applications, CandidateAnalysisService candidateAnalysis,
            JsonMapper json) {
        this.applications = applications;
        this.candidateAnalysis = candidateAnalysis;
        this.json = json;
    }

    @ApplicationModuleListener
    void on(JobFinished event) {
        JobResult result = event.result();
        if (!ApplicationAgent.ANALYZE_JOB.equals(result.type())) {
            return;
        }
        UUID applicationId = UUID.fromString(result.target());
        if (result.status() == JobStatus.DONE) {
            try {
                ApplicationAnalysis analysis = json.treeToValue(result.result(), ApplicationAnalysis.class);
                applications.recordAnalysis(applicationId, analysis);
                judgeTalents(applicationId);
                return;
            } catch (RuntimeException exception) {
                log.warn("Application analysis result for {} could not be read", applicationId, exception);
            }
        } else {
            log.warn("Application analysis failed for {}: {}", applicationId, result.error());
        }
        applications.markAnalysisFailed(applicationId);
    }

    private void judgeTalents(UUID applicationId) {
        try {
            candidateAnalysis.judgeTalents(applicationId);
        } catch (RuntimeException exception) {
            log.warn("Talent fit for {} could not be judged: {}", applicationId, exception.getMessage());
        }
    }
}
