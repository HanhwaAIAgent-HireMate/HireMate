package com.hiremate.recruit.domain;

import com.hiremate.recruit.GuideMethod;
import com.hiremate.recruit.StageGuide;
import com.hiremate.recruit.StageIcon;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
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
    @Column(length = 30)
    private StageIcon icon;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private StageStatus status;

    private Instant confirmedAt;

    private UUID confirmedBy;

    @Column(length = 100)
    private String confirmedByName;

    private Instant doneAt;

    /** 전형 안내. 일정 · 시각 · 진행 방식은 정하지 않았으면 null이다. */
    private LocalDate guideSchedule;

    /** 면접이 아닌 전형의 시작 시각. 면접은 지원자마다 시간을 배정해 늘 비워 둔다. */
    private LocalTime guideTime;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private GuideMethod guideMethod;

    @Column(nullable = false, length = 500)
    private String guidePlace = "";

    @Column(nullable = false, length = 1000)
    private String guidePreparation = "";

    @Column(nullable = false, length = 1000)
    private String guideNote = "";

    public Stage(UUID recruitmentId, int seq, String name, StageType type, StageGuide guide) {
        this(recruitmentId, seq, name, type, guide, null);
    }

    public Stage(UUID recruitmentId, int seq, String name, StageType type, StageGuide guide, StageIcon icon) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.seq = seq;
        this.name = name;
        this.type = type;
        this.icon = icon;
        this.status = StageStatus.PENDING;
        changeGuide(guide);
    }

    public StageGuide guide() {
        return new StageGuide(guideSchedule, guideTime, guideMethod, guidePlace, guidePreparation, guideNote);
    }

    public void changeGuide(StageGuide guide) {
        this.guideSchedule = guide.schedule();
        this.guideTime = type == StageType.INTERVIEW ? null : guide.time();
        this.guideMethod = guide.method();
        this.guidePlace = guide.place();
        this.guidePreparation = guide.preparation();
        this.guideNote = guide.note();
    }

    public void activate() {
        this.status = StageStatus.ACTIVE;
    }

    public void confirm(UUID memberId, String memberName) {
        this.status = StageStatus.CONFIRMED;
        this.confirmedAt = Instant.now();
        this.confirmedBy = memberId;
        this.confirmedByName = memberName;
    }

    public void finish() {
        this.status = StageStatus.DONE;
        this.doneAt = Instant.now();
    }
}
