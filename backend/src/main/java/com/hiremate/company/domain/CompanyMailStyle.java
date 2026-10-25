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

/** 기업의 메일 꾸밈. 색이나 로고가 비어 있으면 기본 색과 회사 이름 글자를 쓴다. */
@Entity
@Table(name = "company_mail_styles")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CompanyMailStyle {

    @Id
    private UUID companyId;

    @Column(length = 7)
    private String color;

    private UUID logoFileId;

    @Column(nullable = false)
    private Instant updatedAt;

    public CompanyMailStyle(UUID companyId) {
        this.companyId = companyId;
        this.updatedAt = Instant.now();
    }

    public void changeColor(String color) {
        this.color = color;
        this.updatedAt = Instant.now();
    }

    /** 로고를 바꾸거나(null이면) 뺀다. */
    public void changeLogo(UUID logoFileId) {
        this.logoFileId = logoFileId;
        this.updatedAt = Instant.now();
    }
}
