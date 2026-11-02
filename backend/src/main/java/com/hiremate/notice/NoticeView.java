package com.hiremate.notice;

import com.hiremate.company.NoticeTemplateType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 안내 초안 하나. 본문은 인사말 · 내용(AI 작성 영역) · 안내 · 맺음말 순서이고 필수 문구는 바꾸지 않는다.
 * guide는 본문 아래에 붙는 안내로, 다음 전형 안내는 다음 전형의 안내(없으면 빈 문자열), 최종 합격 안내는
 * 입사 안내(없으면 담당자가 따로 안내한다는 문장)다. guideMissing은 그 안내의 비어 있는 칸 이름(기타 안내 제외)으로
 * 보내기 전에 경고한다. onboarding은 최종 합격 안내 화면에서 고치는 입사 안내다.
 * nextStageId는 다음 전형 안내가 안내하는 다음 전형으로, 이 화면에서 그 전형의 안내를 고친다. 다른 안내는 null이다.
 */
public record NoticeView(UUID noticeId, UUID stageId, NoticeGroup group, NoticeTemplateType templateType,
        String label, String subject, String greeting, String content, String guide, List<String> guideMissing,
        OnboardingGuide onboarding, String closing, String requiredText,
        int recipientCount, NoticeStatus status, int sentCount, int failedCount,
        @Schema(nullable = true) Instant sentAt, @Schema(nullable = true) UUID nextStageId) {
}
