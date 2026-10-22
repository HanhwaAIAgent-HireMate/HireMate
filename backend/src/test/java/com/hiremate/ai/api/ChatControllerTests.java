package com.hiremate.ai.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.hiremate.ai.application.ChatService;
import com.hiremate.global.AuthenticatedMember;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

class ChatControllerTests {

    @Test
    @DisplayName("Chat 스트림은 시간 제한 없이 Root 답과 반영을 기다린다")
    void chatStreamHasNoTimeout() {
        ChatController controller = new ChatController(mock(ChatService.class), command -> { });
        AuthenticatedMember member = new AuthenticatedMember() {
            @Override
            public UUID memberId() {
                return UUID.randomUUID();
            }

            @Override
            public UUID companyId() {
                return UUID.randomUUID();
            }

            @Override
            public String name() {
                return "최은영";
            }
        };

        SseEmitter emitter = controller.chat(member, UUID.randomUUID(),
                new ChatController.ChatRequest("강점 요약해줘", List.of(), List.of()));

        // 서블릿 규약에서 0 이하는 시간 제한 없음이다
        assertThat(emitter.getTimeout()).isZero();
    }
}
