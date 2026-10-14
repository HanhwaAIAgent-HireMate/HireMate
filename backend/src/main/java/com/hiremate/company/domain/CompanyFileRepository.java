package com.hiremate.company.domain;

import com.hiremate.company.CompanyFileCategory;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyFileRepository extends JpaRepository<CompanyFile, UUID> {

    List<CompanyFile> findByCompanyIdAndCategoryOrderByCreatedAt(UUID companyId, CompanyFileCategory category);

    Optional<CompanyFile> findByFileIdAndCompanyId(UUID fileId, UUID companyId);
}
