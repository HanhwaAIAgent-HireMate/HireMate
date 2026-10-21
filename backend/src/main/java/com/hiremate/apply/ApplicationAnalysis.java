package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * Application Agent가 정리한 지원자 요약. 리스트에는 경력 연수와 마지막 회사를, 서류 전형에서는 서류 점수 · 자격요건 통과 ·
 * 점수 보류로 AI 추천 순위를 매긴다.
 *
 * @param careerYears 서류를 읽지 못하면 null, 신입은 0
 * @param lastCompany 신입이거나 찾지 못하면 null
 * @param documentScore 점수를 보류하면 null
 * @param passed 자격요건을 75% 이상 채웠는가
 * @param held 서류 점수를 보류했는가. 보류한 지원자는 AI 추천 순위에서 빠진다
 * @param shortfalls 채우지 못한 자격요건의 짧은 표시 (예: 신입). 지원자 이름 옆에 붙는다
 */
public record ApplicationAnalysis(@Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, @Schema(nullable = true) Integer documentScore, boolean passed,
        boolean held, List<String> shortfalls) {

    public ApplicationAnalysis {
        shortfalls = shortfalls == null ? List.of() : List.copyOf(shortfalls);
    }
}
