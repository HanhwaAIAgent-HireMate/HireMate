package com.hiremate.screening.domain;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StageRequirementRepository extends JpaRepository<StageRequirement, UUID> {
}
