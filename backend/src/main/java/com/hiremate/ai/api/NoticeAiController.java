package com.hiremate.ai.api;

import com.hiremate.ai.application.NoticeAiService;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.notice.NoticeGroup;
import com.hiremate.notice.NoticeView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 안내 초안 작성과 AI 수정 요청 (MSG-01). */
@RestController
public class NoticeAiController {

    private final NoticeAiService service;

    public NoticeAiController(NoticeAiService service) {
        this.service = service;
    }

    @PostMapping("/api/stages/{stageId}/notices/prepare")
    public List<NoticeView> prepare(AuthenticatedMember member, @PathVariable UUID stageId) {
        return service.prepare(member.companyId(), stageId);
    }

    @PostMapping("/api/stages/{stageId}/notices/{group}/ai-requests")
    public NoticeAiService.NoticeAiAnswer revise(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable NoticeGroup group, @Valid @RequestBody NoticeAiRequest request) {
        return service.revise(member.companyId(), stageId, group, request.message());
    }

    public record NoticeAiRequest(@NotBlank @Size(max = 1000) String message) {
    }
}
