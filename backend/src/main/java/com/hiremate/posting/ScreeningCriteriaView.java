package com.hiremate.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 서류 평가 기준 입력값. 공고의 자격요건 · 우대사항을 순서대로 놓고 저장한 기준을 문장으로 짝짓는다.
 *
 * @param locked 게시한 뒤라 고칠 수 없다
 * @param hireCount 선발 인원. 입력하기 전에는 null이다
 * @param criteriaVersion 평가 기준 버전. 입력하기 전에는 null이다
 * @param items 공고 순서대로 자격요건 다음 우대사항. 항목 번호는 공고 순서로 다시 붙인다
 */
public record ScreeningCriteriaView(boolean locked, @Schema(nullable = true) Integer hireCount,
        @Schema(nullable = true) String criteriaVersion, List<CriterionItem> items) {

    /**
     * @param saved 기준을 저장했는지. false면 서류 평가는 공고 문장 그대로 충족 · 미충족만 판정한다
     * @param criterion 저장한 기준. 저장하지 않은 항목은 중요 표시 없는 단일 능력 · 경험형에 판정 기준이 비어 있다
     */
    public record CriterionItem(boolean saved, ScreeningRubric.Criterion criterion) {
    }
}
