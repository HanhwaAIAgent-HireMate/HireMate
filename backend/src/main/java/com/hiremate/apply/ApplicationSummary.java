package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 접수 현황의 지원자 한 줄: 지원 일시와 제출 자료. */
public record ApplicationSummary(UUID applicationId, int applicationNo, String name, Instant submittedAt,
        List<DocumentType> documents) {
}
