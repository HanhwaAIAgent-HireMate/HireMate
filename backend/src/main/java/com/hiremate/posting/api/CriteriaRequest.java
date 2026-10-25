package com.hiremate.posting.api;

import com.hiremate.posting.ScreeningRubric;
import com.hiremate.posting.ScreeningRubric.Category;
import com.hiremate.posting.ScreeningRubric.CriterionType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 서류 평가 기준 저장. 기준을 입력한 항목만 보낸다. 항목 문장은 공고의 자격요건 · 우대사항과 같아야 한다.
 *
 * @param hireCount 선발 인원. 서류 전형의 AI 추천은 이 인원의 10배수까지다
 */
public record CriteriaRequest(@NotNull @Min(1) @Max(1000) Integer hireCount,
        @NotNull @Size(max = 60) List<@NotNull @Valid CriterionInput> criteria) {

    /**
     * @param partial 부분 충족 기준. 복합 경험형에만 쓰고 다른 유형이면 버린다
     * @param ncsUnitCode 판정 기준 초안을 쓸 때 참고한 NCS 능력단위코드
     */
    public record CriterionInput(@NotNull Category category, @NotBlank @Size(max = 300) String text, boolean important,
            @NotNull CriterionType criterionType, @NotBlank @Size(max = 500) String met,
            @Size(max = 500) String partial, @NotBlank @Size(max = 500) String unmet,
            @Size(max = 10) List<@NotBlank @Size(max = 100) String> certificates,
            @Size(max = 30) String ncsUnitCode) {

        /** 항목 번호는 서비스가 공고 순서로 붙인다. */
        public ScreeningRubric.Criterion toCriterion() {
            boolean composite = criterionType == CriterionType.COMPOSITE;
            String partialRule = composite && partial != null && !partial.isBlank() ? partial.strip() : null;
            List<String> names = certificates == null ? List.of() : certificates.stream().map(String::strip).toList();
            String code = ncsUnitCode == null || ncsUnitCode.isBlank() ? null : ncsUnitCode.strip();
            return new ScreeningRubric.Criterion("", category, text.strip(), important, criterionType,
                    new ScreeningRubric.EvaluationRules(met.strip(), partialRule, unmet.strip()), names, code);
        }
    }
}
