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
 * 전형 대상 지원자와 HR 결정(decision). 선택 지원자는 탭마다 따로 둔다({@link TabSelection}).
 * 결정은 HR이 버튼으로만 바꾼다.
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

    public void promote() {
        this.promoted = true;
    }

    /** 결정한 지원자는 탭의 선택 지원자에 보이지 않는다. 탭에 남은 행은 되돌릴 때를 위해 둔다. */
    public void decide(Decision decision, UUID memberId) {
        this.decision = decision;
        this.decidedBy = memberId;
        this.decidedAt = Instant.now();
    }

    public void revert() {
        this.decision = Decision.PENDING;
        this.decidedBy = null;
        this.decidedAt = null;
    }

    public void confirm() {
        this.undecidedAtConfirm = decision == Decision.PENDING;
        this.finalResult = decision == Decision.PASS ? Decision.PASS : Decision.FAIL;
    }

    public void changeMemo(String memo) {
        this.memo = memo;
    }

    public void changeScore(BigDecimal score) {
        this.score = score;
    }
}
