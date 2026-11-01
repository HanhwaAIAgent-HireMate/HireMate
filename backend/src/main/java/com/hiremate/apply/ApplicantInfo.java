package com.hiremate.apply;

import com.fasterxml.jackson.annotation.JsonIgnore;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 전형 화면의 지원자 한 명. 분석 전이면 경력 · 점수가 null이다.
 *
 * @param documentScore 서류 평가 총점 (자격요건 + 우대사항, 소수 첫째 자리). 보류면 null
 * @param passed 자격요건 75% 통과가 확정됐는가
 * @param held 총점을 보류했는가. 보류면 documentScore가 null이다
 * @param shortfalls 채우지 못했거나 확인이 필요한 자격요건의 짧은 표시 (예: 신입, 경력 확인 필요)
 * @param qualificationStatus 75% 통과 판단. 분석 전이면 UNDETERMINED
 * @param criterionMarks 평가 항목 ID별 판정. 분석 전이면 비어 있다
 * @param highTalents 상으로 판정한 인재상 제목. 판정 전이면 비어 있다 (항목별 판정과 함께 backend 안에서만 쓴다)
 */
public record ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
        @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany,
        @Schema(nullable = true) BigDecimal documentScore, @Schema(nullable = true) BigDecimal documentScoreLow,
        boolean passed, boolean held, List<String> shortfalls,
        QualificationStatus qualificationStatus, @Schema(nullable = true) BigDecimal qualificationScore,
        @Schema(nullable = true) BigDecimal qualificationScoreLow, int qualificationMax,
        @Schema(nullable = true) BigDecimal preferenceScore, int preferenceMax,
        AnalysisStatus analysisStatus, Instant submittedAt, @JsonIgnore Map<String, CriterionMark> criterionMarks,
        @JsonIgnore List<String> highTalents) {

    public ApplicantInfo {
        criterionMarks = criterionMarks == null ? Map.of() : Map.copyOf(criterionMarks);
        highTalents = highTalents == null ? List.of() : List.copyOf(highTalents);
    }

    /** 항목별 판정이 없는 지원자 (테스트). */
    public ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
            Integer careerYears, String lastCompany, BigDecimal documentScore, BigDecimal documentScoreLow,
            boolean passed, boolean held, List<String> shortfalls, QualificationStatus qualificationStatus,
            BigDecimal qualificationScore, BigDecimal qualificationScoreLow, int qualificationMax,
            BigDecimal preferenceScore, int preferenceMax, AnalysisStatus analysisStatus, Instant submittedAt) {
        this(applicationId, recruitmentId, applicationNo, name, email, careerYears, lastCompany, documentScore,
                documentScoreLow, passed, held, shortfalls, qualificationStatus, qualificationScore,
                qualificationScoreLow, qualificationMax, preferenceScore, preferenceMax, analysisStatus, submittedAt,
                Map.of(), List.of());
    }
}
