package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;

/**
 * Application Agent가 정리한 지원자 요약. 서류 평가 점수는 자격요건 50점 + 우대사항 50점이다 (한 영역만 있으면 그 영역이
 * 100점). 75% 통과 판단(qualificationStatus)과 총점 확정 여부(held)는 따로 둔다.
 *
 * @param careerYears 서류를 읽지 못했거나 경력을 확인하지 못하면 null, 신입은 0
 * @param lastCompany 신입이거나 찾지 못하면 null
 * @param criteriaVersion 평가에 쓴 평가 기준 버전
 * @param qualificationRate 자격요건 충족률(%). 확인 필요 항목이 있으면 null
 * @param qualificationScore 자격요건 점수. 확인 필요 항목이 있으면 null
 * @param qualificationMax 자격요건 만점 (50, 우대사항이 없으면 100)
 * @param documentScore 총점(0~100, 소수 첫째 자리). 보류면 null
 * @param passed qualificationStatus가 PASSED인가
 * @param held 총점을 보류했는가 (서류를 읽지 못함 · 확인 필요가 남음). 보류한 지원자는 AI 추천 순위에서 빠진다
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요). 이름 옆에 붙는다
 */
public record ApplicationAnalysis(@Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, @Schema(nullable = true) String criteriaVersion,
        QualificationStatus qualificationStatus, @Schema(nullable = true) BigDecimal qualificationRate,
        @Schema(nullable = true) BigDecimal qualificationScore, int qualificationMax,
        @Schema(nullable = true) BigDecimal preferenceScore, int preferenceMax,
        @Schema(nullable = true) BigDecimal documentScore, boolean passed, boolean held, List<String> shortfalls) {

    public ApplicationAnalysis {
        shortfalls = shortfalls == null ? List.of() : List.copyOf(shortfalls);
    }

    /** 영역 점수 없이 총점만 있는 요약 (stub · 테스트). 자격요건 50 · 우대사항 50으로 둔다. */
    public static ApplicationAnalysis of(Integer careerYears, String lastCompany, BigDecimal documentScore,
            boolean passed, boolean held, List<String> shortfalls) {
        return new ApplicationAnalysis(careerYears, lastCompany, null,
                passed ? QualificationStatus.PASSED : QualificationStatus.FAILED, null, null, 50, null, 50,
                documentScore, passed, held, shortfalls);
    }
}
