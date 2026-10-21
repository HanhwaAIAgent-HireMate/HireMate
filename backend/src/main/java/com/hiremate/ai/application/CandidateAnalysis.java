package com.hiremate.ai.application;

import com.hiremate.posting.DocumentType;
import java.util.List;

/**
 * 지원자 카드의 AI 분석 요약. 모든 항목에 근거 문장과 출처를 붙이고, 근거가 없으면 확인 필요로 둔다 (NFR-03).
 *
 * @param conditions 공고 조건 충족 여부
 * @param notable 눈여겨볼 점
 * @param checks 확인이 필요한 점
 * @param holds 서류 점수를 보류한 이유. 보류가 아니면 비어 있다
 * @param fit AI 적합도 점수(0~100)의 항목별 점수와 이유. 분석 전이거나 보류면 비어 있다
 * @param highlights 문서 Viewer에 표시할 근거 문장
 */
public record CandidateAnalysis(List<Condition> conditions, List<Finding> notable, List<Finding> checks,
        List<Finding> holds, List<FitLine> fit, List<Evidence> highlights, String agent, boolean stub) {

    /** AI 적합도 점수의 한 항목. 예: 직무 실무 경험 8/10. */
    public record FitLine(String label, int points, int max, String reason) {
    }

    public record Condition(String label, boolean met, String requirement) {
    }

    public record Finding(String text, String source) {
    }

    public record Evidence(DocumentType document, String sentence) {
    }
}
