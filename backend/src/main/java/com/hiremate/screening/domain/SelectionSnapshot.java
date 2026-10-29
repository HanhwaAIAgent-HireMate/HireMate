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

/** 탭의 교체 · 좁히기 · 비우기 직전 선택 지원자. [되돌리기]로 돌아간다. 탭마다 하나다. */
@Entity
@Table(name = "selection_snapshots")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SelectionSnapshot {

    @Id
    private UUID tabId;

    /** [{"applicationId": "...", "ai": true}] */
    @Column(nullable = false)
    private String entries;

    @Column(nullable = false)
    private Instant createdAt;

    public SelectionSnapshot(UUID tabId, String entries) {
        this.tabId = tabId;
        this.entries = entries;
        this.createdAt = Instant.now();
    }

    public void replace(String entries) {
        this.entries = entries;
        this.createdAt = Instant.now();
    }
}
