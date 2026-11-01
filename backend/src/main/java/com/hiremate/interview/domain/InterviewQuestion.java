package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.QuestionSource;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "interview_questions")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewQuestion {

    @Version
    private long version;

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID stageId;

    @Column(nullable = false)
    private UUID applicationId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private int seq;

    @Column(nullable = false, length = 500)
    private String text;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private QuestionSource source;

    @Column(nullable = false)
    private String answer = "";

    @Column(columnDefinition = "text")
    private String reason;

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private InterviewerRole interviewerRole;

    /** 🎤 꼬리질문이면 원래 질문의 id. 처음 만든 질문은 null (최대 2단계: 질문 → 꼬리질문 → 꼬리질문의 꼬리질문) */
    private UUID parentQuestionId;

    /** 💾 자동 저장만 되고 아직 답변 분석에 넘기지 않았으면 true. 다른 질문으로 넘어갈 때 분석하고 false로 돌린다. */
    @Column(nullable = false)
    private boolean answerPendingAnalysis;

    @Column(nullable = false)
    private Instant updatedAt;

    public InterviewQuestion(UUID stageId, UUID applicationId, UUID companyId, int seq, String text,
            QuestionSource source) {
        this(stageId, applicationId, companyId, seq, text, source, null);
    }

    public InterviewQuestion(UUID stageId, UUID applicationId, UUID companyId, int seq, String text,
            QuestionSource source, String reason) {
        this(stageId, applicationId, companyId, seq, text, source, reason, null);
    }

    public InterviewQuestion(UUID stageId, UUID applicationId, UUID companyId, int seq, String text,
            QuestionSource source, String reason, InterviewerRole interviewerRole) {
        this(stageId, applicationId, companyId, seq, text, source, reason, interviewerRole, null);
    }

    /** 🎤 꼬리질문을 만들 때 쓴다. 담당은 원래 질문을 따라간다. */
    public InterviewQuestion(UUID stageId, UUID applicationId, UUID companyId, int seq, String text,
            QuestionSource source, String reason, InterviewerRole interviewerRole, UUID parentQuestionId) {
        this.parentQuestionId = parentQuestionId;
        this.interviewerRole = interviewerRole;
        this.id = UUID.randomUUID();
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
        this.seq = seq;
        this.text = text;
        this.source = source;
        this.reason = reason;
        this.updatedAt = Instant.now();
    }

    public void assignRole(InterviewerRole role) {
        this.interviewerRole = role;
        this.updatedAt = Instant.now();
    }

    public void answer(String answer) {
        this.answer = answer;
        this.updatedAt = Instant.now();
    }

    /** 💾 자동 저장: 답변만 바꾸고 분석은 뒤로 미룬다. */
    public void saveDraft(String answer) {
        answer(answer);
        this.answerPendingAnalysis = true;
    }

    /** 미뤄 둔 분석을 넘겼다고 표시한다. */
    public void markAnalyzed() {
        this.answerPendingAnalysis = false;
    }
}
