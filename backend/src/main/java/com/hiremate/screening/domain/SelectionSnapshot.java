package com.hiremate.screening.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 교체 · 좁히기 직전의 선택 지원자. [되돌리기]로 돌아간다. */
@Entity
@Table(name = "selection_snapshots")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SelectionSnapshot {

    @Id
    private UUID stageId;

    /** [{"applicationId": "...", "ai": true}] */
    @Column(nullable = false)
    private String entries;

    @Column(nullable = false)
    private Instant createdAt;

    public SelectionSnapshot(UUID stageId, String entries) {
        this.stageId = stageId;
        this.entries = entries;
        this.createdAt = Instant.now();
    }

    public void replace(String entries) {
        this.entries = entries;
        this.createdAt = Instant.now();
    }
}
