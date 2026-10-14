package com.hiremate.apply;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 전형 화면의 지원자 한 명. 분석 전이면 경력 · 점수가 null이다. */
public record ApplicantInfo(UUID applicationId, UUID recruitmentId, int applicationNo, String name, String email,
        @Schema(nullable = true) Integer careerYears, @Schema(nullable = true) String lastCompany,
        @Schema(nullable = true) Integer documentScore, boolean passed, AnalysisStatus analysisStatus,
        Instant submittedAt) {
}
