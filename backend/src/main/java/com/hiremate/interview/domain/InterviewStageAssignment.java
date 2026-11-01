package com.hiremate.interview.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "interview_stage_assignments")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewStageAssignment {

    @Id
    private UUID stageId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID hrMemberId;

    @Column(nullable = false)
    private UUID practicalMemberId;

    @Version
    private long version;

    public InterviewStageAssignment(UUID companyId, UUID stageId, UUID hrMemberId, UUID practicalMemberId) {
        this.companyId = companyId;
        this.stageId = stageId;
        assign(hrMemberId, practicalMemberId);
    }

    public void assign(UUID hrMemberId, UUID practicalMemberId) {
        this.hrMemberId = hrMemberId;
        this.practicalMemberId = practicalMemberId;
    }
}
