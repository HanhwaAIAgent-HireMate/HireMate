package com.hiremate.recruit.domain;

import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
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
@Table(name = "stages")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Stage {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID recruitmentId;

    @Column(nullable = false)
    private int seq;

    @Column(nullable = false, length = 50)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private StageType type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private StageStatus status;

    private Instant confirmedAt;

    private UUID confirmedBy;

    private Instant doneAt;

    public Stage(UUID recruitmentId, int seq, String name, StageType type) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.seq = seq;
        this.name = name;
        this.type = type;
        this.status = StageStatus.PENDING;
    }

    public void activate() {
        this.status = StageStatus.ACTIVE;
    }

    public void confirm(UUID memberId) {
        this.status = StageStatus.CONFIRMED;
        this.confirmedAt = Instant.now();
        this.confirmedBy = memberId;
    }

    public void finish() {
        this.status = StageStatus.DONE;
        this.doneAt = Instant.now();
    }
}
