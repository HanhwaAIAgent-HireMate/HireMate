package com.hiremate.notice.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 지원자별 발송 결과. 이미 보낸 지원자에게는 다시 보내지 않는다 (NFR-06). */
@Entity
@Table(name = "notice_deliveries")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NoticeDelivery {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID noticeId;

    @Column(nullable = false)
    private UUID applicationId;

    @Column(nullable = false, length = 254)
    private String email;

    @Column(nullable = false, length = 10)
    private String status;

    private String error;

    @Column(nullable = false)
    private Instant sentAt;

    public NoticeDelivery(UUID noticeId, UUID applicationId, String email) {
        this.id = UUID.randomUUID();
        this.noticeId = noticeId;
        this.applicationId = applicationId;
        this.email = email;
        this.status = "FAILED";
        this.sentAt = Instant.now();
    }

    public void result(boolean sent, String error) {
        this.status = sent ? "SENT" : "FAILED";
        this.error = sent ? null : error;
        this.sentAt = Instant.now();
    }

    public boolean isSent() {
        return "SENT".equals(status);
    }
}
