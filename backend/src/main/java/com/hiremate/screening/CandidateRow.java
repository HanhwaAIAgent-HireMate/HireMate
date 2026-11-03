package com.hiremate.screening;

import com.hiremate.apply.AnalysisStatus;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

/**
 * 리스트 · 선택 지원자 카드의 한 줄. 이름과 경력 · 마지막 회사를 보여 주고, 평가 전형은 평가 점수를 붙인다 (FR-18).
 * 서류 전형은 점수를 매기지 않고 평가 항목 충족 개수와 필수 조건으로 줄 세운다.
 *
 * @param aboveLine 서류 전형에서 필수 조건을 모두 충족했거나 HR이 ↑로 올린 지원자. 선 위 지원자만 선택 지원자(AI 단계)에 넣는다
 * @param aiSelected 선택 지원자에 있고 AI가 고른 지원자 (보라 테두리)
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요). 이름 옆에 붙는다
 * @param metCount 서류 전형에서 자격요건 + 우대사항 가운데 충족한 개수
 * @param criterionTotal 자격요건 + 우대사항 항목 수. 서류 전형이 아니면 0
 * @param talentCount 상으로 판정한 인재상 개수. 판정 전이면 0
 * @param talentTotal 기업 인재상 수. 서류 전형이 아니면 0
 * @param missingRequired 충족하지 못했거나 확인이 필요한 필수 조건의 평가 항목 ID
 */
public record CandidateRow(UUID applicationId, String name, @Schema(nullable = true) Integer careerYears,
        @Schema(nullable = true) String lastCompany, Decision decision, boolean selected, boolean aiSelected,
        boolean aboveLine, @Schema(nullable = true) BigDecimal score, AnalysisStatus analysisStatus,
        List<String> shortfalls, int metCount, int criterionTotal, int talentCount, int talentTotal,
        List<String> missingRequired) {

    /** 면접관에게 보낼 줄: 이번 전형의 결정과 선택 표시를 뺀다 (면접관은 결정에 끌려가지 않고 면접한다). */
    public CandidateRow hideDecision() {
        return new CandidateRow(applicationId, name, careerYears, lastCompany, Decision.PENDING, false, false,
                aboveLine, score, analysisStatus, shortfalls, metCount, criterionTotal, talentCount, talentTotal,
                missingRequired);
    }
}
