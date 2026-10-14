package com.hiremate.notice;

import com.hiremate.company.NoticeTemplateType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 안내 초안 하나. 본문은 인사말 · 내용(AI 작성 영역) · 맺음말 순서이고 필수 문구는 바꾸지 않는다. */
public record NoticeView(UUID noticeId, UUID stageId, NoticeGroup group, NoticeTemplateType templateType,
        String label, String subject, String greeting, String content, String closing, String requiredText,
        int recipientCount, NoticeStatus status, int sentCount, int failedCount,
        @Schema(nullable = true) Instant sentAt) {
}
