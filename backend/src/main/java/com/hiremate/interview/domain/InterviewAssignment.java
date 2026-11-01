package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewerRole;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 면접 전형의 담당(인사 · 실무)에 지정한 면접관 계정 하나. */
@Entity
@Table(name = "interview_assignments")
@IdClass(InterviewAssignment.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewAssignment {

    @Id
    private UUID stageId;

    @Id
    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private InterviewerRole interviewerRole;

    @Id
    private UUID memberId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private Instant assignedAt;

    public InterviewAssignment(UUID stageId, InterviewerRole interviewerRole, UUID memberId, UUID companyId) {
        this.stageId = stageId;
        this.interviewerRole = interviewerRole;
        this.memberId = memberId;
        this.companyId = companyId;
        this.assignedAt = Instant.now();
    }

    public record Key(UUID stageId, InterviewerRole interviewerRole, UUID memberId) implements Serializable {

        public Key() {
            this(null, null, null);
        }
    }
}
