package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.InterviewAnalysisInput;
import com.hiremate.ai.application.InterviewAnalyst;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** 개발용 면접 답변 분석. 지원자 프로필은 ai 서버에 있으므로 분석하거나 저장하지 않고 '정리할 답변 없음'으로 답한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.INTERVIEW_ANALYST, mode = AiMode.STUB)
class StubInterviewAnalyst implements InterviewAnalyst {

    @Override
    public Optional<AnalyzeResult> analyze(InterviewAnalysisInput input) {
        return Optional.of(new AnalyzeResult("CHECK", 0, 0));
    }
}
