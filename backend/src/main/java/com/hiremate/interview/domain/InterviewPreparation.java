package com.hiremate.interview.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.NoArgsConstructor;

/** 자료 준비부터 질문 저장까지의 지원자별 진행 상태. 완료·실패하면 제거한다. */
@Entity
@Table(name = "interview_preparations")
@IdClass(InterviewPreparation.Key.class)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewPreparation {

    @Id
    private UUID stageId;

    @Id
    private UUID applicationId;

    @Column(nullable = false)
    private UUID companyId;

    public InterviewPreparation(UUID stageId, UUID applicationId, UUID companyId) {
        this.stageId = stageId;
        this.applicationId = applicationId;
        this.companyId = companyId;
    }

    public record Key(UUID stageId, UUID applicationId) implements Serializable {
        public Key() {
            this(null, null);
        }
    }
}
