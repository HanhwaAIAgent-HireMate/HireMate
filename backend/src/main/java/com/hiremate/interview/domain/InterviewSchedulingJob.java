package com.hiremate.interview.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 결과 확정 뒤 다음 면접 일정 배정의 진행·실패 상태. 지원자별 시간은 interview_schedules가 보관한다. */
@Entity
@Table(name = "interview_scheduling_jobs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewSchedulingJob {

    @Id
    private UUID previousStageId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID nextStageId;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(length = 80)
    private String errorCode;

    public InterviewSchedulingJob(UUID previousStageId, UUID companyId, UUID nextStageId) {
        this.previousStageId = previousStageId;
        this.companyId = companyId;
        this.nextStageId = nextStageId;
    }

    public void change(String status, String errorCode) {
        this.status = status;
        this.errorCode = errorCode;
    }
}
