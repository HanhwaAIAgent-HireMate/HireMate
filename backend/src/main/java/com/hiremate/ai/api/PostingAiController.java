package com.hiremate.ai.api;

import com.hiremate.ai.application.PostingAiService;
import com.hiremate.global.AuthenticatedMember;
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
        return service.request(member.companyId(), recruitmentId, request.message());
    }

    public record PostingAiRequest(@NotBlank @Size(max = 1000) String message) {
    }
}
