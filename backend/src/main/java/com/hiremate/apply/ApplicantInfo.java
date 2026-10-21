package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 전형 화면의 지원자 한 명. 분석 전이면 경력 · 점수가 null이다.
 *
 * @param passed 자격요건을 75% 이상 채웠는가
 * @param held 서류 점수를 보류했는가. 보류면 documentScore가 null이다
 * @param shortfalls 채우지 못한 자격요건의 짧은 표시 (예: 신입)
 */
public record ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
        @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany,
        @Schema(nullable = true) Integer documentScore, boolean passed, boolean held, List<String> shortfalls,
        AnalysisStatus analysisStatus, Instant submittedAt) {
}
