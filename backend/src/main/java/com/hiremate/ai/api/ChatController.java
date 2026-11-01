package com.hiremate.ai.api;

import com.hiremate.ai.application.ChatAnswer;
import com.hiremate.ai.application.ChatAsker;
import com.hiremate.ai.application.ChatInput;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatService;
import com.hiremate.ai.application.ChatStatus;
import com.hiremate.ai.application.ChatTurn;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.screening.StageTabService;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 전형 화면의 AI Chat. 기본 범위는 현재 채용과 전형이고, @멘션과 체크한 지원자로 대상을 좁힌다.
 *
 * <p>질문은 SSE로 답한다. 처리 중 단계(status)와 검증된 항목(item)을 먼저 보내고 done에 답을 보낸다.
 * 탭의 첫 대화면 done 뒤에 자동으로 바꾼 탭 이름(title)을 보낸다.
 * 실패는 error 이벤트다. 전형을 찾을 수 없거나 입력이 틀리면 스트림을 열기 전에 오류 응답(JSON)으로 답한다.
 */
@RestController
public class ChatController {

    private static final Logger log = LoggerFactory.getLogger(ChatController.class);
    // 시간 제한 없음 (서블릿 규약에서 0 이하). 진행은 화면에 보이고, 화면이 떠나면 연결 끊김으로 멈춘다
    private static final long NO_TIMEOUT = 0L;

    private final ChatService chat;
    private final Executor executor;
    private final StageTabService tabs;

    public ChatController(ChatService chat, @Qualifier("chatExecutor") Executor executor, StageTabService tabs) {
        this.chat = chat;
        this.executor = executor;
        this.tabs = tabs;
    }

    @PostMapping("/api/stages/{stageId}/tabs/{tabId}/chat")
    @ApiResponse(responseCode = "200", description = "SSE. status · item · done · error 이벤트",
            content = @Content(mediaType = MediaType.TEXT_EVENT_STREAM_VALUE, schema = @Schema(oneOf = {
                    ChatStatus.class, ChatItem.class, ChatAnswer.class, ChatTitle.class, ChatError.class})))
    public SseEmitter chat(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId,
            @Valid @RequestBody ChatRequest request) {
        // HR은 공유 탭, 면접관은 자기 탭만 쓴다. 면접관 Chat은 배정된 지원자만 보고 선택 지원자를 바꾸지 않는다
        tabs.requireAccess(member, stageId, tabId);
        ChatInput input = chat.prepare(member.companyId(), stageId, tabId,
                new ChatAsker(member.memberId(), member.name()), request.message(), request.mentionIds(),
                request.checkedIds(), member.hr() ? null : member.memberId());
        SseEmitter emitter = new SseEmitter(NO_TIMEOUT);
        executor.execute(() -> answer(emitter, input));
        return emitter;
    }

    private void answer(SseEmitter emitter, ChatInput input) {
        EmitterProgress progress = new EmitterProgress(emitter);
        try {
            ChatAnswer answer = chat.run(input, progress);
            progress.sendQuietly("done", answer);
            // 답은 이미 보냈다. 제목을 짓지 못해도 답은 그대로다
            chat.title(input, answer).ifPresent(tab -> progress.sendQuietly("title", new ChatTitle(tab.id(),
                    tab.name())));
        } catch (UncheckedIOException gone) {
            log.info("Chat client disconnected before the answer: stage {}", input.stageId());
        } catch (ApiException exception) {
            progress.sendQuietly("error", new ChatError(exception.status().value(), exception.code()));
        } catch (RuntimeException exception) {
            log.error("Chat failed: stage {}", input.stageId(), exception);
            progress.sendQuietly("error", new ChatError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "INTERNAL_ERROR"));
        }
        emitter.complete();
    }

    /** 탭의 대화 기록. 같은 기업 담당자가 함께 보고, 탭을 지울 때 지워진다. */
    @GetMapping("/api/stages/{stageId}/tabs/{tabId}/chat")
    public List<ChatTurn> history(AuthenticatedMember member, @PathVariable UUID stageId, @PathVariable UUID tabId) {
        tabs.requireAccess(member, stageId, tabId);
        return chat.history(member.companyId(), stageId, tabId);
    }

    /** title 이벤트 data. 탭의 첫 대화로 자동으로 바꾼 탭 이름이다. */
    public record ChatTitle(UUID tabId, String name) {
    }

    /** error 이벤트 data. status는 같은 오류를 일반 응답으로 냈을 때의 HTTP 상태다. */
    public record ChatError(int status, String code) {
    }

    public record ChatRequest(@NotBlank @Size(max = 2000) String message,
            @NotNull @Size(max = 20) List<@NotNull UUID> mentionIds,
            @NotNull @Size(max = 500) List<@NotNull UUID> checkedIds) {
    }
}
