package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 전형 화면의 지원자 한 명. 분석 전이면 경력 · 점수가 null이다.
 *
 * @param documentScore 서류 평가 총점 (자격요건 + 우대사항, 소수 첫째 자리). 보류면 null
 * @param passed 자격요건 75% 통과가 확정됐는가
 * @param held 총점을 보류했는가. 보류면 documentScore가 null이다
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
 * @param qualificationStatus 75% 통과 판단. 분석 전이면 UNDETERMINED
 */
public record ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
        @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany,
        @Schema(nullable = true) BigDecimal documentScore, boolean passed, boolean held, List<String> shortfalls,
        QualificationStatus qualificationStatus, @Schema(nullable = true) BigDecimal qualificationScore,
        int qualificationMax, @Schema(nullable = true) BigDecimal preferenceScore, int preferenceMax,
        AnalysisStatus analysisStatus, Instant submittedAt) {
}
