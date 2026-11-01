package com.hiremate.screening;

import java.util.List;

/**
 * 서류 전형의 필수 조건. 필수 조건을 모두 충족한 지원자만 선 위(AI 단계)에 오른다. 비어 있으면 분석이 끝난 지원자 모두 오른다.
 *
 * @param criterionIds 필수로 체크한 평가 항목 ID (자격요건 · 우대사항)
 */
public record StageRequirements(List<String> criterionIds) {

    public StageRequirements {
        criterionIds = criterionIds == null ? List.of() : List.copyOf(criterionIds);
    }
}
