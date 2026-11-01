package com.hiremate.auth.domain;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MemberRepository extends JpaRepository<Member, UUID> {

    Optional<Member> findByEmail(String normalizedEmail);

    List<Member> findByCompanyIdOrderByCreatedAt(UUID companyId);

    Optional<Member> findByIdAndCompanyId(UUID id, UUID companyId);
}
