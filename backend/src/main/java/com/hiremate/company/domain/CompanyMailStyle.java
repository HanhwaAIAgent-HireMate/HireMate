package com.hiremate.company.domain;

import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
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

/**
 * 기업의 메일 꾸밈. 색이나 로고가 비어 있으면 기본 색과 회사 이름 글자를 쓴다.
 * 보조 색이 비어 있으면 안내 상자에도 대표 색을 쓴다.
 */
@Entity
@Table(name = "company_mail_styles")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CompanyMailStyle {

    @Id
    private UUID companyId;

    @Column(length = 7)
    private String color;

    @Column(length = 7)
    private String accentColor;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Header header = Header.LINE;

    @Enumerated(EnumType.STRING)
    @Column(name = "guide_box", nullable = false, length = 10)
    private GuideBox guideBox = GuideBox.FILL;

    private UUID logoFileId;

    private UUID bannerFileId;

    @Column(nullable = false)
    private Instant updatedAt;

    public CompanyMailStyle(UUID companyId) {
        this.companyId = companyId;
        this.updatedAt = Instant.now();
    }

    /** 색과 부품을 한 번에 바꾼다. 보조 색은 null이면 뺀다. */
    public void changeLook(String color, String accentColor, Header header, GuideBox guideBox) {
        this.color = color;
        this.accentColor = accentColor;
        this.header = header;
        this.guideBox = guideBox;
        this.updatedAt = Instant.now();
    }

    /** 로고를 바꾸거나(null이면) 뺀다. */
    public void changeLogo(UUID logoFileId) {
        this.logoFileId = logoFileId;
        this.updatedAt = Instant.now();
    }

    /** 배너를 바꾸거나(null이면) 뺀다. */
    public void changeBanner(UUID bannerFileId) {
        this.bannerFileId = bannerFileId;
        this.updatedAt = Instant.now();
    }
}
