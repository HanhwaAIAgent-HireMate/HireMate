package com.hiremate.ai.application;

import java.util.Optional;
import java.util.UUID;

/**
 * Interview Agent (면접 답변 분석). 질문별 답변에서 확인된 점 · 아직 확인되지 않은 점 · 어긋나는 점을 근거와 함께 ai 서버의
 * 지원자 프로필에 저장한다 (FR-28). 결정은 바꾸지 않고, 결과는 화면에 따로 보여 주지 않는다 (프로필에만 저장).
 *
 * <p>stub은 결과를 바로 돌려준다. remote는 분석 작업을 대기열(job 모듈)에 넣고 빈 값을 돌려주며, AI 워커가 분석해
 * 프로필에 저장한다.
 */
public interface InterviewAnalyst {

    /** 대기열 작업 유형. ai 서버 경로(/agents/interview-analyst/analyze)와 같다. 작업 대상은 {@link #jobTarget}이다. */
    String ANALYZE_JOB = "interview-analyst/analyze";

    Optional<AnalyzeResult> analyze(InterviewAnalysisInput input);

    /** 면접 답변 분석 작업의 대상. 다시 분석할 때 기록을 다시 읽도록 '기업 ID:전형 ID:지원서 ID'로 적는다. */
    static String jobTarget(UUID companyId, UUID stageId, UUID applicationId) {
        return companyId + ":" + stageId + ":" + applicationId;
    }

    /**
     * 분석 결과 요약.
     *
     * @param status DONE(정리함), CHECK(기록한 답변 없음), FAILED(모델이 답하지 못함)
     * @param saved 이 전형의 면접 항목으로 프로필에 남은 수
     * @param dropped 근거를 답변 원문에서 찾지 못하는 등 검사를 통과하지 못해 버린 항목 수
     */
    record AnalyzeResult(String status, int saved, int dropped) {
    }
}
