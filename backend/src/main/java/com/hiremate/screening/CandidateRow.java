package com.hiremate.screening;

import com.hiremate.apply.AnalysisStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

/**
 * 리스트 · 선택 지원자 카드의 한 줄. 이름과 경력 · 마지막 회사를 보여 주고, 평가 전형은 평가 점수를,
 * 서류 전형은 AI 적합도 점수를 붙인다 (FR-18).
 *
 * @param aboveLine 서류 전형에서 AI 추천(선발 인원 10배수 안)에 들었거나 HR이 ↑로 올린 지원자
 * @param aiSelected 선택 지원자에 있고 AI가 고른 지원자 (보라 테두리)
 * @param held 서류 전형에서 점수를 보류한 지원자. AI 추천 바로 뒤에 연한 회색으로 보인다
 * @param shortfalls 채우지 못한 자격요건의 짧은 표시 (예: 신입). 서류 전형에서 이름 옆에 붙는다
 * @param documentScore 서류 전형의 AI 적합도 점수(100점). 분석 전이거나 보류면 null이다
 */
public record CandidateRow(UUID applicationId, String name, @Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, Decision decision, boolean selected, boolean aiSelected,
        boolean aboveLine, @Schema(nullable = true) BigDecimal score, AnalysisStatus analysisStatus, boolean held,
        List<String> shortfalls, @Schema(nullable = true) Integer documentScore) {
}
