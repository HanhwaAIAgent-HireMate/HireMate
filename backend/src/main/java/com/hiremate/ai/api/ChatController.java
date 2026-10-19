package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatAnswer;
import com.hiremate.ai.application.ChatService;
import com.hiremate.ai.application.ChatTurn;
import com.hiremate.global.AuthenticatedMember;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 전형 화면의 AI Chat. 기본 범위는 현재 채용과 전형이고, @멘션과 체크한 지원자로 대상을 좁힌다. */
@RestController
public class ChatController {

    private final ChatService chat;

    public ChatController(ChatService chat) {
        this.chat = chat;
    }

    @PostMapping("/api/stages/{stageId}/chat")
    public ChatAnswer chat(AuthenticatedMember member, @PathVariable UUID stageId,
            @Valid @RequestBody ChatRequest request) {
        return chat.chat(member.companyId(), stageId, member.memberId(), request.message(), request.mentionIds(),
                request.checkedIds());
    }

    /** 담당자의 이 전형 대화 기록. 전형이 끝나면 지워진다. */
    @GetMapping("/api/stages/{stageId}/chat")
    public List<ChatTurn> history(AuthenticatedMember member, @PathVariable UUID stageId) {
        return chat.history(member.companyId(), stageId, member.memberId());
    }

    @DeleteMapping("/api/stages/{stageId}/chat")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void forget(AuthenticatedMember member, @PathVariable UUID stageId) {
        chat.forget(member.companyId(), stageId, member.memberId());
    }

    public record ChatRequest(@NotBlank @Size(max = 2000) String message,
            @NotNull @Size(max = 20) List<@NotNull UUID> mentionIds,
            @NotNull @Size(max = 500) List<@NotNull UUID> checkedIds) {
    }
}
