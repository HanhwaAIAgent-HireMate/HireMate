package com.hiremate.ai.application;

import com.hiremate.posting.DocumentType;
import java.util.List;

/**
 * 지원자 카드의 AI 분석 요약. 모든 항목에 근거 문장과 출처를 붙이고, 근거가 없으면 확인 필요로 둔다 (NFR-03).
 *
 * @param conditions 공고 조건 충족 여부
 * @param notable 눈여겨볼 점
 * @param checks 확인이 필요한 점
 * @param highlights 문서 Viewer에 표시할 근거 문장
 */
public record CandidateAnalysis(List<Condition> conditions, List<Finding> notable, List<Finding> checks,
        List<Evidence> highlights, String agent, boolean stub) {

    public record Condition(String label, boolean met, String requirement) {
    }

    public record Finding(String text, String source) {
    }

    public record Evidence(DocumentType document, String sentence) {
    }
}
