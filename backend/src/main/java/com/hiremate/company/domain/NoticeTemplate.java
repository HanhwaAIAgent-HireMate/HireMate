package com.hiremate.company.domain;

import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "notice_templates")
@IdClass(NoticeTemplate.Key.class)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NoticeTemplate {

    @Id
    private UUID companyId;

    @Id
    @Enumerated(EnumType.STRING)
    private NoticeTemplateType type;

    @Column(nullable = false, length = 200)
    private String subject;

    @Column(nullable = false)
    private String greeting;

    @Column(nullable = false, length = 200)
    private String aiGuide;

    @Column(nullable = false)
    private String closing;

    @Column(nullable = false)
    private String requiredText;

    @Column(nullable = false)
    private Instant updatedAt;

    public NoticeTemplate(UUID companyId, NoticeTemplateInfo info) {
        this.companyId = companyId;
        this.type = info.type();
        update(info);
    }

    public void update(NoticeTemplateInfo info) {
        this.subject = info.subject();
        this.greeting = info.greeting();
        this.aiGuide = info.aiGuide();
        this.closing = info.closing();
        this.requiredText = info.requiredText();
        this.updatedAt = Instant.now();
    }

    public NoticeTemplateInfo toInfo() {
        return new NoticeTemplateInfo(type, subject, greeting, aiGuide, closing, requiredText);
    }

    public record Key(UUID companyId, NoticeTemplateType type) implements Serializable {

        public Key() {
            this(null, null);
        }
    }
}
