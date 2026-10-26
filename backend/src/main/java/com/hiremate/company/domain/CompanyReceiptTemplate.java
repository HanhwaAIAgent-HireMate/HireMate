package com.hiremate.company.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 기업이 정한 접수 확인 메일 양식. 없으면 기본 문장을 쓴다. */
@Entity
@Table(name = "company_receipt_templates")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CompanyReceiptTemplate {

    @Id
    private UUID companyId;

    @Column(nullable = false, length = 200)
    private String subject;

    @Column(nullable = false, length = 5000)
    private String body;

    @Column(nullable = false)
    private Instant updatedAt;

    public CompanyReceiptTemplate(UUID companyId, String subject, String body) {
        this.companyId = companyId;
        change(subject, body);
    }

    public void change(String subject, String body) {
        this.subject = subject;
        this.body = body;
        this.updatedAt = Instant.now();
    }
}
