package com.hiremate.ai.application;

import java.util.List;
import java.util.UUID;

/**
 * 지원자 한 명의 면접 전형 기록. 질문과 답변은 interview 모듈이 저장한 그대로다.
 *
 * @param questions 이번 면접 전형의 질문과 답변. 답변을 기록하지 않았으면 answer가 빈 문자열이다
 * @param previous 같은 지원자의 이전 면접 전형 기록. 이번 답변과 비교할 맥락으로만 쓴다
 */
public record InterviewAnalysisInput(UUID companyId, UUID recruitmentId, UUID stageId, UUID applicationId,
        String stageName, List<AnsweredQuestion> questions, List<PreviousInterview> previous) {

    public record AnsweredQuestion(String text, String answer) {
    }

    public record PreviousInterview(String stageName, List<AnsweredQuestion> questions) {
    }
}
