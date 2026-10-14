package com.hiremate.report;

import java.time.Instant;
import java.util.UUID;

public record ReportView(UUID recruitmentId, String title, Instant generatedAt, String agent,
        ReportContent content) {
}
