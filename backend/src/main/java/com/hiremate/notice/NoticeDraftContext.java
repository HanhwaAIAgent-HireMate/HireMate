package com.hiremate.notice;

import com.hiremate.company.NoticeTemplateType;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/** Communication Agent가 내용을 쓸 때 쓰는 정보. */
public record NoticeDraftContext(UUID noticeId, NoticeTemplateType templateType, String companyName,
        String recruitmentTitle, String stageName, @Schema(nullable = true) String nextStageName, String aiGuide,
        String content) {
}
