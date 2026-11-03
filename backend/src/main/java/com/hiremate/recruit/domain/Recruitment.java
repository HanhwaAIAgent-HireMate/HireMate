package com.hiremate.recruit.domain;

import com.hiremate.recruit.RecruitmentStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "recruitments")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Recruitment {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private RecruitmentStatus status;

    private UUID currentStageId;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant publishedAt;

    private Instant closedAt;

    private Instant deletedAt;

    public void archive() {
        this.deletedAt = Instant.now();
    }

    public Recruitment(UUID companyId, String title) {
        this.id = UUID.randomUUID();
        this.companyId = companyId;
        this.title = title;
        this.status = RecruitmentStatus.DRAFT;
        this.createdAt = Instant.now();
    }

    public void rename(String title) {
        this.title = title;
    }

    public void publish() {
        this.status = RecruitmentStatus.PUBLISHED;
        this.publishedAt = Instant.now();
    }

    public void moveTo(UUID stageId) {
        this.status = RecruitmentStatus.IN_PROGRESS;
        this.currentStageId = stageId;
    }

    public void close() {
        this.status = RecruitmentStatus.CLOSED;
        this.closedAt = Instant.now();
    }
}
