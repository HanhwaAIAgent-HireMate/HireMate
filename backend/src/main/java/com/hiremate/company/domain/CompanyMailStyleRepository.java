package com.hiremate.company.domain;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyMailStyleRepository extends JpaRepository<CompanyMailStyle, UUID> {
}
