package com.hiremate.posting.domain;

import com.hiremate.global.JsonText;
import com.hiremate.global.StringListConverter;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingRole;
import com.hiremate.posting.RequiredCriteria;
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

    /** 서류 필수 조건으로 표시한 자격 요건 줄. 지원자에게 보여 주지 않는다. */
    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> requiredQualifications = new ArrayList<>();

    /** 서류 필수 조건으로 표시한 우대 사항 줄. 지원자에게 보여 주지 않는다. */
    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> requiredPreferred = new ArrayList<>();

    /** 블라인드 채용. 켜면 학력 칸을 비우고, 학력 · 출신 학교 조건을 쓰지 않는다. */
    @Column(nullable = false)
    private boolean blind;

    /** 모집 조건. 채용 인원은 정하지 않았으면 null이다. */
    private Integer headcount;

    @Column(nullable = false, length = 50)
    private String position = "";

    @Column(nullable = false, length = 50)
    private String education = "";

    @Column(nullable = false, length = 100)
    private String workHours = "";

    @Column(nullable = false, length = 100)
    private String salary = "";

    private String roleContent;

    public record Roles(List<PostingRole> items) {
    }

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

    private String posterDesign;

    public PosterDesign design() {
        return JsonText.read(posterDesign, PosterDesign.class);
    }

    public void changeDesign(PosterDesign design) {
        this.posterDesign = JsonText.write(design);
        this.updatedAt = Instant.now();
    }

    private Instant openAt;

    private Instant closeAt;

    private Instant publishedAt;

    private UUID publishedBy;

    private Instant closedAt;

    @Column(nullable = false)
    private Instant updatedAt;

    public JobPosting(UUID recruitmentId, UUID companyId, String title, String location, String intro,
            List<String> benefits, List<String> notices) {
        this.id = UUID.randomUUID();
        this.recruitmentId = recruitmentId;
        this.companyId = companyId;
        this.title = title;
        this.location = location;
        this.intro = intro;
        this.benefits = new ArrayList<>(benefits);
        this.notices = new ArrayList<>(notices);
        this.updatedAt = Instant.now();
    }

    public PostingContent content() {
        return new PostingContent(title, jobCategory, employmentType, career, location, intro, List.copyOf(duties),
                List.copyOf(qualifications), List.copyOf(preferred), List.copyOf(benefits), headcount, position,
                education, workHours, salary,
                roleContent == null ? List.of() : JsonText.read(roleContent, Roles.class).items(), blind);
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
        this.headcount = content.headcount();
        this.position = content.position();
        this.education = blind ? "" : content.education();
        this.workHours = content.workHours();
        this.salary = content.salary();
        this.roleContent = JsonText.write(new Roles(content.roles()));
        markRequired(required());
    }

    /** 서류 필수 조건. 공고에 있는 줄만 남긴다 (RequiredCriteria#within). */
    public boolean isBlind() {
        return blind;
    }

    /**
     * 블라인드를 켜면 학력 칸을 비운다. 공고 작성 중에만 부른다 (게시하면 공고 전체가 잠긴다).
     * update는 본문의 blind를 보지 않아, 블라인드 여부는 이 메서드로만 바뀐다.
     */
    public void changeBlind(boolean blind) {
        this.blind = blind;
        if (blind) {
            this.education = "";
        }
        this.updatedAt = Instant.now();
    }

    public RequiredCriteria required() {
        return new RequiredCriteria(requiredQualifications, requiredPreferred);
    }

    public void markRequired(RequiredCriteria required) {
        RequiredCriteria kept = required.within(content());
        this.requiredQualifications = new ArrayList<>(kept.qualifications());
        this.requiredPreferred = new ArrayList<>(kept.preferred());
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
