package com.hiremate.posting.domain;

import com.hiremate.global.StringListConverter;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ReceiptTemplate;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "job_postings")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class JobPosting {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private UUID recruitmentId;

    @Column(nullable = false)
    private UUID companyId;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 100)
    private String jobCategory = "";

    @Column(nullable = false, length = 50)
    private String employmentType = "";

    @Column(nullable = false, length = 50)
    private String career = "";

    @Column(nullable = false, length = 100)
    private String location = "";

    @Column(nullable = false)
    private String intro = "";

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> duties = new ArrayList<>();

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> qualifications = new ArrayList<>();

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> preferred = new ArrayList<>();

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> benefits = new ArrayList<>();

    /** 설정의 필수 안내 문구. 공고를 만들 때 채우고 HR 요청으로만 바뀐다. */
    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> notices = new ArrayList<>();

    /** 필수로 받는 추가 서류(PORTFOLIO, CERTIFICATE). 이력서 · 자기소개서는 항상 필수다. */
    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> requiredExtras = new ArrayList<>();

    /** 적용 전 AI 수정안 (JSON). */
    private String pendingSuggestion;

    private Instant openAt;

    private Instant closeAt;

    private Instant publishedAt;

    private UUID publishedBy;

    private Instant closedAt;

    @Column(nullable = false)
    private Instant updatedAt;

    @Column(nullable = false, length = 200)
    private String receiptSubject = "";

    @Column(nullable = false, length = 5000)
    private String receiptBody = "";

    public JobPosting(UUID recruitmentId, UUID companyId, String title, String intro, List<String> benefits,
            List<String> notices) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.title = title;
        this.intro = intro;
        this.benefits = new ArrayList<>(benefits);
        this.notices = new ArrayList<>(notices);
        this.updatedAt = Instant.now();
        changeReceipt(ReceiptTemplate.DEFAULT);
    }

    /** 접수 확인 메일. 이 칸을 더하기 전에 만든 공고는 비어 있어 기본 문장을 쓴다. */
    public ReceiptTemplate receipt() {
        return receiptSubject.isBlank() || receiptBody.isBlank()
                ? ReceiptTemplate.DEFAULT
                : new ReceiptTemplate(receiptSubject, receiptBody);
    }

    public void changeReceipt(ReceiptTemplate receipt) {
        this.receiptSubject = receipt.subject();
        this.receiptBody = receipt.body();
        this.updatedAt = Instant.now();
    }

    public PostingContent content() {
        return new PostingContent(title, jobCategory, employmentType, career, location, intro, List.copyOf(duties),
                List.copyOf(qualifications), List.copyOf(preferred), List.copyOf(benefits));
    }

    public void update(PostingContent content) {
        this.title = content.title();
        this.jobCategory = content.jobCategory();
        this.employmentType = content.employmentType();
        this.career = content.career();
        this.location = content.location();
        this.intro = content.intro();
        this.duties = new ArrayList<>(content.duties());
        this.qualifications = new ArrayList<>(content.qualifications());
        this.preferred = new ArrayList<>(content.preferred());
        this.benefits = new ArrayList<>(content.benefits());
        this.updatedAt = Instant.now();
    }

    public void changeRequiredExtras(List<String> extras) {
        this.requiredExtras = new ArrayList<>(extras);
        this.updatedAt = Instant.now();
    }

    public void suggest(String suggestionJson) {
        this.pendingSuggestion = suggestionJson;
    }

    public void clearSuggestion() {
        this.pendingSuggestion = null;
    }

    public void publish(Instant openAt, Instant closeAt, UUID memberId) {
        this.openAt = openAt;
        this.closeAt = closeAt;
        this.publishedAt = Instant.now();
        this.publishedBy = memberId;
        this.pendingSuggestion = null;
    }

    public void close() {
        this.closedAt = Instant.now();
    }
}
