package com.hiremate.notice.domain;

import com.hiremate.notice.NoticeGroup;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NoticeRepository extends JpaRepository<Notice, UUID> {

    List<Notice> findByStageIdAndCompanyIdOrderByGroupTypeDesc(UUID stageId, UUID companyId);

    Optional<Notice> findByStageIdAndCompanyIdAndGroupType(UUID stageId, UUID companyId, NoticeGroup groupType);
}
