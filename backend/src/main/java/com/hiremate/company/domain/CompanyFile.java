package com.hiremate.company.domain;

import com.hiremate.company.CompanyFileCategory;
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
@Table(name = "company_files")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CompanyFile {

    @Id
    private UUID fileId;

    @Column(nullable = false)
    private UUID companyId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CompanyFileCategory category;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private long sizeBytes;

    @Column(nullable = false)
    private Instant createdAt;

    public CompanyFile(UUID fileId, UUID companyId, CompanyFileCategory category, String name, long sizeBytes) {
        this.fileId = fileId;
        this.companyId = companyId;
        this.category = category;
        this.name = name;
        this.sizeBytes = sizeBytes;
        this.createdAt = Instant.now();
    }
}
