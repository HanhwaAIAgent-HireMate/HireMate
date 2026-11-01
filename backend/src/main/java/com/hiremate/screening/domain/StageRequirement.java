package com.hiremate.screening.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 서류 전형에서 HR이 체크한 필수 조건. 전형마다 하나이고, 없으면 공고 기준의 중요 표시를 쓴다. */
@Entity
@Table(name = "stage_requirements")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class StageRequirement {

    @Id
    private UUID stageId;

    @Column(nullable = false)
    private UUID companyId;

    /** 평가 항목 ID. 줄바꿈으로 나눈다. */
    @Column(nullable = false)
    private String criterionIds;

    @Column(nullable = false)
    private Instant updatedAt;

    public StageRequirement(UUID stageId, UUID companyId, Collection<String> criterionIds) {
        this.stageId = stageId;
        this.companyId = companyId;
        replace(criterionIds);
    }

    public List<String> criterionIds() {
        return criterionIds.isEmpty() ? List.of() : List.of(criterionIds.split("\n"));
    }

    public void replace(Collection<String> criterionIds) {
        this.criterionIds = String.join("\n", criterionIds);
        this.updatedAt = Instant.now();
    }
}
