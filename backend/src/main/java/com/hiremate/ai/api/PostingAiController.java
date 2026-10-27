package com.hiremate.ai.api;

import com.hiremate.ai.application.PostingAiService;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.PostingFocus;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 공고 편집 화면의 [AI 수정 요청]. 수정안은 HR이 적용해야 공고에 반영된다. */
@RestController
public class PostingAiController {

    private final PostingAiService service;

    public PostingAiController(PostingAiService service) {
        this.service = service;
    }

    @PostMapping("/api/recruitments/{recruitmentId}/posting/ai-requests")
    public PostingAiService.PostingAiAnswer request(AuthenticatedMember member, @PathVariable UUID recruitmentId,
            @Valid @RequestBody PostingAiRequest request) {
        return service.request(member.companyId(), recruitmentId, request.message(), request.focus());
    }

    /** focus는 HR이 줄을 골라 요청할 때만 있고 아니면 null이다. 있으면 AI는 그 줄만 고친다. */
    public record PostingAiRequest(@NotBlank @Size(max = 1000) String message,
            @Valid @Schema(nullable = true) PostingFocus focus) {
    }
}
