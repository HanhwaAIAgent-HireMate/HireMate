package com.hiremate.notice.domain;

import com.hiremate.company.NoticeTemplateType;
import com.hiremate.notice.NoticeGroup;
import com.hiremate.notice.NoticeStatus;
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
@Table(name = "notices")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Notice {

    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID stageId;

    @Column(nullable = false)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID companyId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private NoticeGroup groupType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private NoticeTemplateType templateType;

    @Column(nullable = false, length = 200)
    private String subject;

    @Column(nullable = false)
    private String greeting;

    @Column(nullable = false)
    private String content;

    @Column(nullable = false)
    private String closing;

    @Column(nullable = false)
    private String requiredText;

    @Column(nullable = false)
    private int recipientCount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private NoticeStatus status;

    @Column(nullable = false)
    private int sentCount;

    @Column(nullable = false)
    private int failedCount;

    private Instant sentAt;

    private UUID sentBy;

    @Column(nullable = false)
    private Instant updatedAt;

    public Notice(UUID stageId, UUID recruitmentId, UUID companyId, NoticeGroup groupType,
            NoticeTemplateType templateType, String subject, String greeting, String closing, String requiredText,
            int recipientCount) {
        this.id = UUID.randomUUID();
        this.stageId = stageId;
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.groupType = groupType;
        this.templateType = templateType;
        this.subject = subject;
        this.greeting = greeting;
        this.content = "";
        this.closing = closing;
        this.requiredText = requiredText;
        this.recipientCount = recipientCount;
        this.status = recipientCount == 0 ? NoticeStatus.EMPTY : NoticeStatus.DRAFT;
        this.updatedAt = Instant.now();
    }

    public boolean isEditable() {
        return status == NoticeStatus.DRAFT;
    }

    public void edit(String subject, String greeting, String content, String closing) {
        this.subject = subject;
        this.greeting = greeting;
        this.content = content;
        this.closing = closing;
        this.updatedAt = Instant.now();
    }

    public void recordSending(int sent, int failed, UUID memberId) {
        this.sentCount = sent;
        this.failedCount = failed;
        this.status = failed == 0 ? NoticeStatus.SENT : NoticeStatus.PARTIAL;
        this.sentAt = Instant.now();
        this.sentBy = memberId;
    }

    public boolean isDone() {
        return status == NoticeStatus.SENT || status == NoticeStatus.EMPTY;
    }
}
