package com.hiremate.screening.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * 탭의 선택 지원자 한 명. 선택은 탐색용 표시라 채용 상태를 바꾸지 않는다. 결정한 지원자는 행이 남아도 보이지 않고,
 * 결정을 되돌리면 같은 순서와 AI 표시로 다시 보인다.
 */
@Entity
@Table(name = "tab_selections")
@IdClass(TabSelection.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class TabSelection {

    @Id
    private UUID tabId;

    @Id
    private UUID applicationId;

    /** AI가 고른 지원자 (보라 테두리). */
    @Column(nullable = false)
    private boolean ai;

    @Column(nullable = false)
    private Instant selectedAt;

    public TabSelection(UUID tabId, UUID applicationId, boolean ai) {
        this.tabId = tabId;
        this.applicationId = applicationId;
        this.ai = ai;
        this.selectedAt = Instant.now();
    }

    public void markAi(boolean ai) {
        this.ai = ai;
    }

    public record Key(UUID tabId, UUID applicationId) implements Serializable {

        public Key() {
            this(null, null);
        }
    }
}
