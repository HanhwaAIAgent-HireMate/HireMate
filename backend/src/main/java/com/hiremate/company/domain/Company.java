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

@Entity
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

    public Company(String name) {
        this.id = UUID.randomUUID();
        this.name = name;
        this.createdAt = Instant.now();
    }

    public void updateProfile(String intro, String culture, List<Talent> talents, List<String> benefits) {
        this.intro = intro;
        this.culture = culture;
        this.talents = new ArrayList<>(talents);
        this.benefits = new ArrayList<>(benefits);
    }

    public void updatePostingSettings(String writingStyle, List<String> requiredNotices) {
        this.writingStyle = writingStyle;
        this.requiredNotices = new ArrayList<>(requiredNotices);
    }
}
