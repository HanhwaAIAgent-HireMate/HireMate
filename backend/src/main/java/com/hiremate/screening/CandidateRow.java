package com.hiremate.screening;

import com.hiremate.apply.AnalysisStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

/**
 * 리스트 · 선택 지원자 카드의 한 줄. 이름과 경력 · 마지막 회사만 보여 주고, 평가 전형은 점수를 붙인다 (FR-18).
 *
 * @param aboveLine 서류 전형에서 AI 기준을 넘었거나 HR이 ↑로 올린 지원자
 * @param aiSelected 선택 지원자에 있고 AI가 고른 지원자 (보라 테두리)
 */
public record CandidateRow(UUID applicationId, String name, @Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, Decision decision, boolean selected, boolean aiSelected,
        boolean aboveLine, @Schema(nullable = true) BigDecimal score, AnalysisStatus analysisStatus) {
}
