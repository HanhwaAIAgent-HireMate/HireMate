package com.hiremate.interview.domain;

import com.hiremate.interview.InterviewerRole;
import com.hiremate.interview.Recommendation;
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

/** 면접관 한 명이 지원자 한 명에게 남긴 의견. 담당과 이름은 저장할 때의 값이다. */
@Entity
@Table(name = "interview_opinions")
@IdClass(InterviewOpinion.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewOpinion {

    @Id
    private UUID stageId;

    @Id
    private UUID applicationId;

    @Id
    private UUID memberId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false, length = 100)
    private String memberName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private InterviewerRole interviewerRole;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Recommendation recommendation;

    @Column(nullable = false, columnDefinition = "text")
    private String comment;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    public InterviewOpinion(UUID stageId, UUID applicationId, UUID memberId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.memberId = memberId;
        this.companyId = companyId;
        this.createdAt = Instant.now();
    }

    public void write(String memberName, InterviewerRole role, Recommendation recommendation, String comment) {
        this.memberName = memberName;
        this.interviewerRole = role;
        this.recommendation = recommendation;
        this.comment = comment;
        this.updatedAt = Instant.now();
    }

    /** 처음 저장한 뒤에 고쳤나. */
    public boolean edited() {
        return updatedAt.isAfter(createdAt);
    }

    public record Key(UUID stageId, UUID applicationId, UUID memberId) implements Serializable {

        public Key() {
            this(null, null, null);
        }
    }
}
