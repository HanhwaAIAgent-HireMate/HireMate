package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatProgress;
import com.hiremate.ai.application.PostingAgent;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingFocus;
import com.hiremate.posting.PostingSuggestion;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageDraft;
import com.hiremate.recruit.StageType;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.json.JsonMapper;

class RemotePostingAgentTests {

    private static final PostingContent CONTENT = new PostingContent("백엔드 개발자", "백엔드 개발", "정규직",
            "경력 3년 이상", "서울 중구", "", List.of("API 개발"), List.of(), List.of("금융 도메인 경험"),
            List.of("유연 근무"));
    private static final PostingDraftContext POSTING = new PostingDraftContext(UUID.randomUUID(),
            RecruitmentStatus.DRAFT, CONTENT, List.of(new StageDraft("서류 전형", StageType.DOCUMENT)),
            Set.of(DocumentType.PORTFOLIO));

    /** 진행 알림을 받지 않는다. 어느 진행 알림이 ai 서버 스트림에 넘어갔는지만 비교한다. */
    private static final ChatProgress PROGRESS = new ChatProgress() {
        @Override
        public void status(String text) {
        }

        @Override
        public void item(ChatItem item) {
        }
    };

    @Test
    @DisplayName("ai 서버의 posting/revise 스트림으로 공고, 작성 스타일, 수정 요청을 보내고 진행 알림과 수정안을 받는다")
    void revisesThroughAiServer() {
        PostingAgent.Result answer = new PostingAgent.Result("우대 사항 수정안을 만들었어요.",
                new PostingSuggestion(CONTENT, null, null, List.of("preferred")));
        RecordingClient client = new RecordingClient(answer);

        PostingAgent.Result result = new RemotePostingAgent(client).revise(POSTING, "짧게 쓴다", "우대 사항 다듬어 줘",
                null, PROGRESS);

        assertThat(result).isEqualTo(answer);
        assertThat(client.agent).isEqualTo(AiAgent.POSTING);
        assertThat(client.method).isEqualTo("revise");
        assertThat(client.progress).isSameAs(PROGRESS);
        assertThat(client.body).containsEntry("posting", POSTING)
                .containsEntry("writingStyle", "짧게 쓴다")
                .containsEntry("request", "우대 사항 다듬어 줘")
                .containsEntry("focus", null);
    }

    @Test
    @DisplayName("공고 작성 스타일이 없으면 빈 글로 보낸다")
    void sendsEmptyWritingStyleWhenMissing() {
        RecordingClient client = new RecordingClient(new PostingAgent.Result("어느 칸을 고칠까요?", null));

        new RemotePostingAgent(client).revise(POSTING, null, "음", null, PROGRESS);

        assertThat(client.body).containsEntry("writingStyle", "");
    }

    @Test
    @DisplayName("HR이 고른 줄을 focus로 보낸다")
    void sendsChosenLineAsFocus() {
        RecordingClient client = new RecordingClient(new PostingAgent.Result("우대 사항 1번 줄 수정안을 만들었어요.", null));
        PostingFocus focus = new PostingFocus("preferred", 0);

        new RemotePostingAgent(client).revise(POSTING, "", "더 구체적으로", focus, PROGRESS);

        assertThat(client.body).containsEntry("focus", focus);
    }

    @Test
    @DisplayName("ai 서버 답의 NCS 출처를 읽고, 출처가 없는 답은 빈 목록으로 둔다")
    void readsNcsSourcesFromAiAnswer() {
        JsonMapper mapper = JsonMapper.builder().build();
        String withSources = """
                {"reply": "주요 업무(1줄 추가) 수정안을 만들었어요.", "suggestion": null, "ncsSources": [{
                  "field": "duties", "number": 2, "line": "배치 프로그램 구현", "dutyName": "응용SW엔지니어링",
                  "unitCode": "2001020211_23v6", "unitName": "서버프로그램 구현", "taskName": "배치 프로그램 구현하기",
                  "sentence": "배치 프로그램을 구현 한다"}]}
                """;

        PostingAgent.Result result = mapper.readValue(withSources, PostingAgent.Result.class);
        PostingAgent.Result plain = mapper.readValue("{\"reply\": \"어느 칸을 고칠까요?\", \"suggestion\": null}",
                PostingAgent.Result.class);

        assertThat(result.ncsSources()).containsExactly(new PostingAgent.NcsSource("duties", 2, "배치 프로그램 구현",
                "응용SW엔지니어링", "2001020211_23v6", "서버프로그램 구현", "배치 프로그램 구현하기", "배치 프로그램을 구현 한다"));
        assertThat(plain.ncsSources()).isEmpty();
    }

    /** ai 서버 대신 받은 요청을 기록하고 정해 둔 응답을 돌려준다. */
    private static final class RecordingClient extends AiServerClient {

        private final Object response;
        private AiAgent agent;
        private String method;
        private Map<Object, Object> body;
        private ChatProgress progress;

        RecordingClient(Object response) {
            super(WebClient.builder(), "http://ai.test", Duration.ofSeconds(1), JsonMapper.builder().build());
            this.response = response;
        }

        @Override
        <T> T stream(AiAgent agent, String method, Object body, Class<T> type, ChatProgress progress) {
            this.agent = agent;
            this.method = method;
            this.body = new HashMap<>((Map<?, ?>) body);
            this.progress = progress;
            return type.cast(response);
        }
    }
}
