package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;

/**
 * Application Agent가 정리한 지원자 요약. 서류는 점수를 매기지 않고 평가 항목마다 판정만 남긴다.
 *
 * @param careerYears 서류를 읽지 못했거나 경력을 확인하지 못하면 null, 신입은 0
 * @param lastCompany 신입이거나 찾지 못하면 null
 * @param criteriaVersion 평가에 쓴 평가 기준 버전
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요). 이름 옆에 붙는다
 * @param criterionMarks 평가 항목 ID별 판정. 전체 지원자의 충족 개수 정렬과 필수 조건 확인에 쓴다
 */
public record ApplicationAnalysis(@Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, @Schema(nullable = true) String criteriaVersion,
        List<String> shortfalls, Map<String, CriterionMark> criterionMarks) {

    public ApplicationAnalysis {
        shortfalls = shortfalls == null ? List.of() : List.copyOf(shortfalls);
        criterionMarks = criterionMarks == null ? Map.of() : Map.copyOf(criterionMarks);
    }

    /** 평가 기준 버전 · 항목별 판정 없이 경력과 미충족 표시만 있는 요약 (stub · 테스트). */
    public static ApplicationAnalysis of(Integer careerYears, String lastCompany, List<String> shortfalls) {
        return new ApplicationAnalysis(careerYears, lastCompany, null, shortfalls, Map.of());
    }
}
