package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.AssessmentAgent;
import com.hiremate.ai.application.AssessmentInput;
import org.springframework.stereotype.Component;

/** 개발용 Assessment Agent. 지원자 프로필은 ai 서버에 있으므로 분석하거나 저장하지 않고 '볼 자료 없음'으로 답한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.ASSESSMENT, mode = AiMode.STUB)
class StubAssessmentAgent implements AssessmentAgent {

    @Override
    public AnalyzeResult analyze(AssessmentInput input) {
        return new AnalyzeResult("CHECK", 0, 0);
    }
}
