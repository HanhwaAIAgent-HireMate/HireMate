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

    /** 다음 전형이 면접이면 이 메일로 안내한 면접 일시. 발송 뒤 바뀐 일정을 알아보는 데 쓴다. */
    private Instant interviewAt;

    public NoticeDelivery(UUID noticeId, UUID applicationId, String email) {
        this.id = UUID.randomUUID();
        this.noticeId = noticeId;
        this.applicationId = applicationId;
        this.email = email;
        this.status = "FAILED";
        this.sentAt = Instant.now();
    }

    public void result(boolean sent, String error) {
        result(sent, error, null);
    }

    /** interviewAt은 메일로 안내한 면접 일시다. 면접이 아니면 null이다. */
    public void result(boolean sent, String error, Instant interviewAt) {
        this.status = sent ? "SENT" : "FAILED";
        this.error = sent ? null : error;
        this.sentAt = Instant.now();
        this.interviewAt = interviewAt;
    }

    public boolean isSent() {
        return "SENT".equals(status);
    }
}
