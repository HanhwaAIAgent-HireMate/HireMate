package com.hiremate.apply.domain;

import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

public interface ApplicationDocumentRepository extends JpaRepository<ApplicationDocument, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from ApplicationDocument d where d.id = ?1")
    Optional<ApplicationDocument> findLockedById(UUID id);

    List<ApplicationDocument> findByApplicationId(UUID applicationId);

    List<ApplicationDocument> findByApplicationIdIn(Collection<UUID> applicationIds);

    @Query("select distinct d.applicationId from ApplicationDocument d, JobApplication a where a.id = d.applicationId"
            + " and a.recruitmentId = ?1 and a.companyId = ?2 and lower(d.text) like lower(concat('%', ?3, '%'))")
    List<UUID> searchText(UUID recruitmentId, UUID companyId, String keyword);
}
