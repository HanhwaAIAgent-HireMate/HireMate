package com.hiremate.ai.api;

import com.hiremate.ai.application.InterviewAiService;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewView;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 면접 화면의 [질문 만들기]. */
@RestController
public class InterviewAiController {

    private final InterviewAiService service;

    public InterviewAiController(InterviewAiService service) {
        this.service = service;
    }

    @PostMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/generate")
    public InterviewView generate(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody GenerateRequest request) {
        return service.generate(member.companyId(), stageId, applicationId, request.focus());
    }

    public record GenerateRequest(@Schema(nullable = true) @Size(max = 500) String focus) {
    }
}
