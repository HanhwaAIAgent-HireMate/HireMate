package com.hiremate.apply;

/**
 * Application Agent가 정리한 지원자 요약. 리스트에는 경력 연수와 마지막 회사를, 서류 전형에서는 서류 점수와 AI 기준 통과 여부를 쓴다.
 *
 * @param lastCompany 신입이거나 찾지 못하면 null
 */
public record ApplicationAnalysis(int careerYears, String lastCompany, int documentScore, boolean passed) {
}
