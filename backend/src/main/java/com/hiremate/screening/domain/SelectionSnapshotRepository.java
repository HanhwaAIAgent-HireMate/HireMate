package com.hiremate.screening.domain;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SelectionSnapshotRepository extends JpaRepository<SelectionSnapshot, UUID> {
}
