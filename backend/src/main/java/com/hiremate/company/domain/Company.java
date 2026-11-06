package com.hiremate.company.domain;

import com.hiremate.company.Talent;
import com.hiremate.global.StringListConverter;
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
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
@Table(name = "companies")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Company {

    @Id
    private UUID id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private String intro = "";

    @Column(nullable = false)
    private String culture = "";

    /** 회사 주소. 채용 페이지 맨 아래에 보여 준다. */
    @Column(nullable = false, length = 200)
    private String address = "";

    @Convert(converter = TalentListConverter.class)
    @Column(nullable = false)
    private List<Talent> talents = new ArrayList<>();

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> benefits = new ArrayList<>();

    @Column(nullable = false)
    private String writingStyle = "";

    @Convert(converter = StringListConverter.class)
    @Column(nullable = false)
    private List<String> requiredNotices = new ArrayList<>();

    private String posterBrand;

    /** 회사 소개 · 조직 문화 글에서 AI가 뽑은 인재상 요소. */
    @Convert(converter = TalentListConverter.class)
    @Column(nullable = false)
    private List<Talent> cultureFactors = new ArrayList<>();

    /** cultureFactors를 뽑을 때 읽은 글. 지금 글과 다르면 요소가 낡은 것이다. */
    @Column(nullable = false)
    private String cultureFactorsSource = "";

    public void changePosterBrand(String value) {
        this.posterBrand = value;
    }

    public Company(String name) {
        this.id = UUID.randomUUID();
        this.name = name;
        this.createdAt = Instant.now();
    }

    public void updateProfile(String intro, String culture, List<Talent> talents, List<String> benefits,
            String address) {
        this.intro = intro;
        this.culture = culture;
        this.address = address;
        this.talents = new ArrayList<>(talents);
        this.benefits = new ArrayList<>(benefits);
    }

    /** AI가 회사 글에서 인재상 요소를 찾을 때 읽을 글. */
    public String cultureText() {
        return (intro.strip() + "\n" + culture.strip()).strip();
    }

    /** source가 지금 글과 같을 때만 남긴다. 그 사이 글이 다시 바뀌었으면 새 요청의 결과를 기다린다. */
    public boolean recordCultureFactors(String source, List<Talent> factors) {
        if (!source.equals(cultureText())) {
            return false;
        }
        this.cultureFactors = new ArrayList<>(factors);
        this.cultureFactorsSource = source;
        return true;
    }

    public void updatePostingSettings(String writingStyle, List<String> requiredNotices) {
        this.writingStyle = writingStyle;
        this.requiredNotices = new ArrayList<>(requiredNotices);
    }
}
