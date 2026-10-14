package com.hiremate.assessment;

import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/** 지원자 한 명의 평가 결과와 제출물. 영역 점수는 NCS 5개 영역 이름을 키로 쓴다. */
public record AssessmentResultView(UUID applicationId, @Schema(nullable = true) BigDecimal total,
        Map<String, BigDecimal> areas, @Schema(nullable = true) String grade, @Schema(nullable = true) UUID fileId,
        @Schema(nullable = true) String fileName, @Schema(nullable = true) String url,
        @Schema(nullable = true) String note, String source, Instant registeredAt) {
}
