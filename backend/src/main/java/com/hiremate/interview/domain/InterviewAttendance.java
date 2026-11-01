package com.hiremate.interview.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 면접관 한 명의 면접 입장. 입장한 때와 마지막으로 접속이 확인된 때를 남긴다. */
@Entity
@Table(name = "interview_attendance")
@IdClass(InterviewAttendance.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewAttendance {

    @Id
    private UUID stageId;

    @Id
    private UUID applicationId;

    @Id
    private UUID memberId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private Instant enteredAt;

    @Column(nullable = false)
    private Instant lastSeenAt;

    public InterviewAttendance(UUID stageId, UUID applicationId, UUID memberId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.memberId = memberId;
        this.companyId = companyId;
        this.enteredAt = Instant.now();
        this.lastSeenAt = this.enteredAt;
    }

    public void seen() {
        this.lastSeenAt = Instant.now();
    }

    public record Key(UUID stageId, UUID applicationId, UUID memberId) implements Serializable {

        public Key() {
            this(null, null, null);
        }
    }
}
