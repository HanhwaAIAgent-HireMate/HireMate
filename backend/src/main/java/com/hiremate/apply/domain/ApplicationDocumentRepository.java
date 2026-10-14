package com.hiremate.apply.domain;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApplicationDocumentRepository extends JpaRepository<ApplicationDocument, UUID> {

    List<ApplicationDocument> findByApplicationId(UUID applicationId);

    List<ApplicationDocument> findByApplicationIdIn(Collection<UUID> applicationIds);
}
