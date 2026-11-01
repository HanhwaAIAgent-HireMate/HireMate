package com.hiremate.ai;

import com.hiremate.ai.application.InterviewAiService;
import com.hiremate.interview.InterviewSessions;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 면접관 화면에 공개하는 AI 보조 API. 업무 권한은 모델 호출 전후에 확인한다. */
@Service
public class InterviewAssistance {

    private final InterviewAiService service;
    private final InterviewSessions sessions;

    public InterviewAssistance(InterviewAiService service, InterviewSessions sessions) {
        this.service = service;
        this.sessions = sessions;
    }

    public InterviewerFollowUps suggest(UUID companyId, UUID stageId, UUID questionId, UUID memberId,
            List<String> avoid) {
        sessions.requireQuestionWrite(companyId, stageId, questionId, memberId, true);
        var result = service.followUps(companyId, stageId, questionId, avoid);
        sessions.requireQuestionWrite(companyId, stageId, questionId, memberId, true);
        return new InterviewerFollowUps(result.needed(), result.suggestions().stream()
                .map(item -> new InterviewerSuggestion(item.text(), item.check())).toList());
    }

    public record InterviewerSuggestion(String text, String check) {
    }

    public record InterviewerFollowUps(boolean needed, List<InterviewerSuggestion> suggestions) {
    }
}
