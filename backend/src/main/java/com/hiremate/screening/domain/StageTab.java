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

/**
 * 전형 화면의 탭. 선택 지원자와 AI Chat 대화방의 묶음이고 같은 기업 담당자가 함께 쓴다.
 * 이름은 "새 탭"으로 시작하고, 첫 대화 뒤 자동 제목이 붙거나 담당자가 바꾸면 더 이상 자동으로 바뀌지 않는다.
 */
@Entity
@Table(name = "stage_tabs")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class StageTab {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false)
    private UUID stageId;

    @Column(nullable = false)
    private int number;

    @Column(nullable = false, length = 30)
    private String name;

    @Column(nullable = false)
    private boolean autoNamed;

    @Column(nullable = false)
    private Instant createdAt;

    /** 면접관이 자기만 보는 탭이면 그 계정. 비어 있으면 같은 기업 HR이 함께 쓰는 탭이다 */
    private UUID ownerMemberId;

    public StageTab(UUID companyId, UUID stageId, int number) {
        this(companyId, stageId, number, null);
    }

    public StageTab(UUID companyId, UUID stageId, int number, UUID ownerMemberId) {
        this.ownerMemberId = ownerMemberId;
        this.id = UUID.randomUUID();
        this.companyId = companyId;
        this.stageId = stageId;
        this.number = number;
        this.name = "새 탭";
        this.autoNamed = true;
        this.createdAt = Instant.now();
    }

    public void rename(String name) {
        this.name = name;
        this.autoNamed = false;
    }

    /** 자동 제목. 아직 자동 제목을 기다릴 때만 바꾸고, 바꿨으면 true다. */
    public boolean autoName(String name) {
        if (!autoNamed) {
            return false;
        }
        rename(name);
        return true;
    }
}
