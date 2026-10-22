package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.CommunicationAgent;
import com.hiremate.notice.NoticeDraftContext;
import org.springframework.stereotype.Component;

/** 개발용 Communication Agent. 양식 유형에 맞는 기본 문장을 쓰고, 말투 · 길이 · 덧붙임 요청을 규칙으로 반영한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.COMMUNICATION, mode = AiMode.STUB)
class StubCommunicationAgent implements CommunicationAgent {

    @Override
    public Draft write(NoticeDraftContext notice, String request) {
        String base = notice.content().isBlank() ? initial(notice) : notice.content();
        if (request == null) {
            return new Draft("초안을 만들었어요.", base);
        }
        String[] sentences = base.split("(?<=[.!?。])\\s+");
        if (request.contains("따뜻") || request.contains("부드럽")) {
            int index = Math.min(1, sentences.length - 1);
            sentences[index] = "보내 주신 지원서를 한 줄 한 줄 소중히 읽었습니다. " + sentences[index];
            return new Draft((index + 1) + "번째 문장을 더 따뜻하게 바꿨어요.", String.join(" ", sentences));
        }
        if (request.contains("짧게") || request.contains("간단")) {
            return new Draft("핵심 문장만 남겨 짧게 줄였어요.", sentences[0]);
        }
        int colon = request.indexOf(':');
        String addition = colon >= 0
                ? request.substring(colon + 1).trim()
                : request.replaceAll("(추가|넣어|해)줘\\.?", "").trim();
        return new Draft("요청한 내용을 마지막 문장으로 더했어요.", base + " " + addition);
    }

    private static String initial(NoticeDraftContext notice) {
        return switch (notice.templateType()) {
            case NEXT_STAGE -> notice.stageName() + "에 합격하셨습니다. 축하드립니다. 다음 전형은 "
                    + (notice.nextStageName() == null ? "다음 단계" : notice.nextStageName()) + "입니다.";
            case REJECT -> "검토 결과 아쉽게도 이번 채용에서는 함께하기 어렵게 되었습니다. "
                    + "앞으로의 여정을 진심으로 응원하겠습니다.";
            case FINAL_PASS -> "최종 합격을 진심으로 축하드립니다. 함께하게 되어 기쁩니다.";
            case FINAL_REJECT -> "최종 전형 결과, 아쉽게도 이번에는 함께하지 못하게 되었습니다. "
                    + "긴 전형 동안 성실히 참여해 주셔서 감사합니다.";
        };
    }
}
