package com.hiremate.activity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "activity_logs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ActivityLog {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID companyId;

    private UUID actorId;

    @Column(nullable = false, length = 50)
    private String action;

    @Column(nullable = false, length = 50)
    private String targetType;

    @Column(nullable = false)
    private UUID targetId;

    private String detail;

    @Column(nullable = false)
    private Instant createdAt;

    public ActivityLog(UUID companyId, UUID actorId, String action, String targetType, UUID targetId, String detail) {
        this.id = UUID.randomUUID();
        this.companyId = companyId;
        this.actorId = actorId;
        this.action = action;
        this.targetType = targetType;
        this.targetId = targetId;
        this.detail = detail;
        this.createdAt = Instant.now();
    }
}
