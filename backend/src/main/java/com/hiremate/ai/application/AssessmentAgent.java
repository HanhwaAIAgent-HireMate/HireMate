package com.hiremate.ai.application;

/**
 * Assessment Agent. 평가 자료에서 강점 · 약점과 근거를 뽑아 ai 서버의 지원자 프로필에 저장한다.
 * 점수 · 등급과 결정은 바꾸지 않는다. 결과는 화면에 따로 보여 주지 않는다 (프로필에만 저장).
 */
public interface AssessmentAgent {

    AnalyzeResult analyze(AssessmentInput input);

    /**
     * 분석 결과 요약.
     *
     * @param status DONE(분석함), CHECK(볼 자료 없음), FAILED(모델이 답하지 못함)
     * @param saved 이 전형의 평가 항목으로 프로필에 남은 수
     * @param dropped 근거를 원문에서 찾지 못하는 등 검사를 통과하지 못해 버린 항목 수
     */
    record AnalyzeResult(String status, int saved, int dropped) {
    }
}
