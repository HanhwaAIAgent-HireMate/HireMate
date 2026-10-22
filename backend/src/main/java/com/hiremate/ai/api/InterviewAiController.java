package com.hiremate.ai.api;

import com.hiremate.ai.application.InterviewAiService;
import com.hiremate.global.AuthenticatedMember;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** 면접 카드의 맞춤 질문 생성 상태 (STG-12). 앞 전형 결과를 확정하면 AI 워커가 질문을 미리 만든다 (FR-27). */
@RestController
public class InterviewAiController {

    private final InterviewAiService service;

    public InterviewAiController(InterviewAiService service) {
        this.service = service;
    }

    /** 카드는 만드는 중이면 '질문 생성 중'을 보여 주고, 끝날 때까지 몇 초마다 다시 묻는다. */
    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/preparing")
    public PreparingView preparing(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return new PreparingView(service.preparing(member.companyId(), stageId, applicationId));
    }

    public record PreparingView(boolean preparing) {
    }
}
