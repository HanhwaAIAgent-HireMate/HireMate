package com.hiremate.interview.domain;

import com.hiremate.interview.QuestionSource;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
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

    @Column(nullable = false)
    private Instant updatedAt;

    public InterviewQuestion(UUID stageId, UUID applicationId, UUID companyId, int seq, String text,
            QuestionSource source) {
        this.id = UUID.randomUUID();
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
        this.seq = seq;
        this.text = text;
        this.source = source;
        this.updatedAt = Instant.now();
    }

    public void answer(String answer) {
        this.answer = answer;
        this.updatedAt = Instant.now();
    }
}
