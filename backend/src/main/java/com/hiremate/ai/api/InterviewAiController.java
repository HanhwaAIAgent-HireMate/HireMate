package com.hiremate.ai.api;

import com.hiremate.ai.application.InterviewAiService;
import com.hiremate.ai.application.InterviewFollowUps;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewSessions;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 면접 카드의 맞춤 질문 생성 상태 (STG-12). 앞 전형 결과를 확정하면 AI 워커가 질문을 미리 만든다 (FR-27). */
@RestController
public class InterviewAiController {

    private final InterviewAiService service;
    private final InterviewSessions sessions;

    public InterviewAiController(InterviewAiService service, InterviewSessions sessions) {
        this.service = service;
        this.sessions = sessions;
    }

    /** 카드는 만드는 중이면 '질문 생성 중'을 보여 주고, 끝날 때까지 몇 초마다 다시 묻는다. */
    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/preparing")
    public PreparingView preparing(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return new PreparingView(service.preparing(member.companyId(), stageId, applicationId));
    }

    public record PreparingView(boolean preparing) {
    }

    /**
     * 🎤 [꼬리질문 받기] · [다시 제안]. 면접관이 버튼을 누를 때만 모델을 부른다. 답이 충분하면 needed가 false다.
     * 제안은 저장하지 않는다. 면접관이 고른 질문은 POST .../follow-ups로 넣는다.
     */
    @PostMapping("/api/stages/{stageId}/interview/questions/{questionId}/follow-ups/suggestions")
    public InterviewFollowUps followUps(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID questionId, @Valid @RequestBody FollowUpsRequest request) {
        sessions.requireQuestionWrite(member.companyId(), stageId, questionId, member.memberId(), false);
        var result = service.followUps(member.companyId(), stageId, questionId, request.avoid());
        sessions.requireQuestionWrite(member.companyId(), stageId, questionId, member.memberId(), false);
        return result;
    }

    /**
     * 꼬리질문 제안 요청.
     *
     * @param avoid [다시 제안]이면 앞서 보여 준 제안 문장. 처음이면 빈 목록
     */
    public record FollowUpsRequest(@NotNull @Size(max = 4) List<@Size(max = 500) String> avoid) {
    }

    /** HR이 요청한 현재 카드의 질문을 백업 없이 삭제하고 처음 구성부터 다시 만든다. */
    @PostMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/questions/regenerate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void regenerate(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID applicationId) {
        service.regenerate(member.companyId(), stageId, applicationId);
    }
}
