package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationService;
import com.hiremate.posting.PostingService;
import com.hiremate.screening.ScreeningService;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CandidateAnalysisService {

    private final ScreeningService screening;
    private final ApplicationService applications;
    private final PostingService postings;
    private final CandidateAnalyst analyst;

    public CandidateAnalysisService(ScreeningService screening, ApplicationService applications,
            PostingService postings, CandidateAnalyst analyst) {
        this.screening = screening;
        this.applications = applications;
        this.postings = postings;
        this.analyst = analyst;
    }

    /** 현재 전형의 대상 지원자만 분석한다. */
    public CandidateAnalysis analyze(UUID companyId, UUID stageId, UUID applicationId) {
        screening.detail(companyId, stageId, applicationId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        return analyst.analyze(applications.detail(companyId, applicationId),
                postings.draftContext(companyId, recruitmentId).content());
    }
}
