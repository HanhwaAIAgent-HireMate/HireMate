package com.hiremate.screening.domain;

import com.hiremate.screening.Decision;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 전형 대상 지원자. 선택 지원자 영역(selected, aiSelected)과 HR 결정(decision)을 따로 둔다.
 * 선택은 탐색용 표시라 채용 상태를 바꾸지 않고, 결정은 HR이 버튼으로만 바꾼다.
 */
@Entity
@Table(name = "stage_candidates")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class StageCandidate {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID stageId;

    @Column(nullable = false)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID applicationId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Decision decision;

    private UUID decidedBy;

    private Instant decidedAt;

    /** 결과 확정 뒤의 최종 결과. 미결정은 불합격으로 확정된다. */
    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Decision finalResult;

    @Column(nullable = false)
    private boolean undecidedAtConfirm;

    @Column(nullable = false)
    private boolean promoted;

    @Column(nullable = false)
    private boolean selected;

    @Column(nullable = false)
    private boolean aiSelected;

    private Instant selectedAt;

    private BigDecimal score;

    @Column(nullable = false)
    private String memo = "";

    public StageCandidate(UUID stageId, UUID recruitmentId, UUID companyId, UUID applicationId) {
        this.id = UUID.randomUUID();
        this.stageId = stageId;
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.applicationId = applicationId;
        this.decision = Decision.PENDING;
    }

    public void select(boolean byAi) {
        if (!selected) {
            this.selectedAt = Instant.now();
        }
        this.selected = true;
        this.aiSelected = byAi;
    }

    public void unselect() {
        this.selected = false;
        this.aiSelected = false;
        this.selectedAt = null;
    }

    public void promote() {
        this.promoted = true;
    }

    /** 결정하면 선택 지원자에서 빠진다. AI 선택 여부는 되돌릴 때를 위해 남긴다. */
    public void decide(Decision decision, UUID memberId) {
        this.decision = decision;
        this.decidedBy = memberId;
        this.decidedAt = Instant.now();
        this.selected = false;
    }

    /** 결정을 되돌리면 선택 지원자로 돌아온다. */
    public void revert() {
        this.decision = Decision.PENDING;
        this.decidedBy = null;
        this.decidedAt = null;
        this.selected = true;
        this.selectedAt = Instant.now();
    }

    public void confirm() {
        this.undecidedAtConfirm = decision == Decision.PENDING;
        this.finalResult = decision == Decision.PASS ? Decision.PASS : Decision.FAIL;
        this.selected = false;
        this.aiSelected = false;
    }

    public void changeMemo(String memo) {
        this.memo = memo;
    }

    public void changeScore(BigDecimal score) {
        this.score = score;
    }

    public boolean isAiMarked() {
        return selected && aiSelected;
    }
}
