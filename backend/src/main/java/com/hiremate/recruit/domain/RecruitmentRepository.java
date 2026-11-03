package com.hiremate.recruit.domain;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RecruitmentRepository extends JpaRepository<Recruitment, UUID> {

    Optional<Recruitment> findByIdAndCompanyIdAndDeletedAtIsNull(UUID id, UUID companyId);

    List<Recruitment> findByCompanyIdAndDeletedAtIsNullOrderByCreatedAtDesc(UUID companyId);
}
