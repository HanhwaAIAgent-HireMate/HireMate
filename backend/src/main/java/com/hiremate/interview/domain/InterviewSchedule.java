package com.hiremate.interview.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
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

    /** 구분값이 없는 기존 일정은 재배정 대상에 넣지 않는다. */
    @Column(nullable = false)
    private boolean automaticallyScheduled;

    @Column(nullable = false, length = 200)
    private String interviewers = "";

    public InterviewSchedule(UUID stageId, UUID applicationId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
    }

    public void change(Instant scheduledAt, String interviewers) {
        if (!Objects.equals(this.scheduledAt, scheduledAt)) {
            automaticallyScheduled = false;
        }
        this.scheduledAt = scheduledAt;
        this.interviewers = interviewers;
    }

    public void assignAutomatically(Instant scheduledAt) {
        this.scheduledAt = scheduledAt;
        automaticallyScheduled = true;
    }

    public record Key(UUID stageId, UUID applicationId) implements Serializable {

        public Key() {
            this(null, null);
        }
    }
}
