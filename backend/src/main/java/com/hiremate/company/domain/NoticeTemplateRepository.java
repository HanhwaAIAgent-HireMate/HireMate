package com.hiremate.company.domain;

import com.hiremate.company.NoticeTemplateType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NoticeTemplateRepository extends JpaRepository<NoticeTemplate, NoticeTemplate.Key> {

    List<NoticeTemplate> findByCompanyId(UUID companyId);

    Optional<NoticeTemplate> findByCompanyIdAndType(UUID companyId, NoticeTemplateType type);
}
