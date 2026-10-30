package com.hiremate.interview;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 면접 전형의 지원자 카드: 일정, 맞춤 질문과 질문별 답변, 이전 면접 기록 (FR-27, FR-28). */
public record InterviewView(UUID applicationId, @Schema(nullable = true) Schedule schedule,
        List<Question> questions, List<PreviousInterview> previous, boolean singleInterview) {

    public InterviewView(UUID applicationId, Schedule schedule, List<Question> questions,
            List<PreviousInterview> previous) {
        this(applicationId, schedule, questions, previous, false);
    }

    /** 면접 일정은 HR이 직접 입력한다 (자동 일정 조율은 MVP 제외). */
    public record Schedule(@Schema(nullable = true) Instant scheduledAt, String interviewers) {
    }

    /**
     * 면접 질문 하나와 기록한 답변.
     *
     * @param parentQuestionId 🎤 꼬리질문이면 원래 질문의 id, 처음 만든 질문은 null. 목록은 원래 질문 바로 뒤에 꼬리질문을 둔다
     */
    public record Question(UUID questionId, String text, QuestionSource source, String answer,
            @Schema(nullable = true) String reason,
            @Schema(nullable = true) InterviewerRole interviewerRole,
            @Schema(nullable = true) UUID parentQuestionId) {

        public Question(UUID questionId, String text, QuestionSource source, String answer, String reason,
                InterviewerRole interviewerRole) {
            this(questionId, text, source, answer, reason, interviewerRole, null);
        }

        public Question(UUID questionId, String text, QuestionSource source, String answer, String reason) {
            this(questionId, text, source, answer, reason, null);
        }

        public Question(UUID questionId, String text, QuestionSource source, String answer) {
            this(questionId, text, source, answer, null);
        }
    }

    public record PreviousInterview(UUID stageId, String stageName, @Schema(nullable = true) Schedule schedule,
            List<Question> questions) {
    }
}
