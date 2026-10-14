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

@Entity
@Table(name = "interview_schedules")
@IdClass(InterviewSchedule.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewSchedule {

    @Id
    private UUID stageId;

    @Id
    private UUID applicationId;

    @Column(nullable = false)
    private UUID companyId;

    private Instant scheduledAt;

    @Column(nullable = false, length = 200)
    private String interviewers = "";

    public InterviewSchedule(UUID stageId, UUID applicationId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
    }

    public void change(Instant scheduledAt, String interviewers) {
        this.scheduledAt = scheduledAt;
        this.interviewers = interviewers;
    }

    public record Key(UUID stageId, UUID applicationId) implements Serializable {

        public Key() {
            this(null, null);
        }
    }
}
