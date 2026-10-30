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

    public record Question(UUID questionId, String text, QuestionSource source, String answer,
            @Schema(nullable = true) String reason,
            @Schema(nullable = true) InterviewerRole interviewerRole) {

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
