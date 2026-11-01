package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalyst;
import com.hiremate.ai.application.CompanyFactors;
import com.hiremate.ai.application.FeatureLabels;
import com.hiremate.ai.application.TalentFit;
import com.hiremate.ai.application.TalentFitRequest;
import com.hiremate.apply.ApplicantDetail;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * ai 서버의 지원자 분석 (POST /agents/candidate-analyst/analyze). {@code HIREMATE_AI_AGENTS_CANDIDATE_ANALYST=remote}로 켠다.
 * ai 서버는 지원 접수 때 저장한 결과를 돌려주고, 없으면 그때 분석한다. 표 보기의 열 이름(labels), 회사 글의 인재상 요소(factors),
 * 인재상 판정(talents)도 맡는다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.CANDIDATE_ANALYST, mode = AiMode.REMOTE)
class RemoteCandidateAnalyst implements CandidateAnalyst {

    private final AiServerClient client;

    RemoteCandidateAnalyst(AiServerClient client) {
        this.client = client;
    }

    @Override
    public CandidateAnalysis analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric) {
        return client.post(AiAgent.CANDIDATE_ANALYST, "analyze",
                Map.of("applicant", applicant, "posting", posting, "rubric", rubric), CandidateAnalysis.class);
    }

    @Override
    public FeatureLabels labels(List<String> texts) {
        return client.post(AiAgent.CANDIDATE_ANALYST, "labels", Map.of("texts", texts), FeatureLabels.class);
    }

    @Override
    public TalentFit talents(TalentFitRequest request) {
        return client.post(AiAgent.CANDIDATE_ANALYST, "talents", request, TalentFit.class);
    }

    @Override
    public CompanyFactors factors(String text) {
        return client.post(AiAgent.CANDIDATE_ANALYST, "factors", Map.of("text", text), CompanyFactors.class);
    }
}
