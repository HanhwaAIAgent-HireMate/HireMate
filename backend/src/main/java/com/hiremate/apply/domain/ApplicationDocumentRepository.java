package com.hiremate.apply.domain;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface ApplicationDocumentRepository extends JpaRepository<ApplicationDocument, UUID> {

    List<ApplicationDocument> findByApplicationId(UUID applicationId);

    List<ApplicationDocument> findByApplicationIdIn(Collection<UUID> applicationIds);

    @Query("select distinct d.applicationId from ApplicationDocument d, JobApplication a where a.id = d.applicationId"
            + " and a.recruitmentId = ?1 and a.companyId = ?2 and lower(d.text) like lower(concat('%', ?3, '%'))")
    List<UUID> searchText(UUID recruitmentId, UUID companyId, String keyword);
}
