package com.hiremate.recruit.domain;

import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StageRepository extends JpaRepository<Stage, UUID> {

    List<Stage> findByRecruitmentIdOrderBySeq(UUID recruitmentId);

    List<Stage> findByRecruitmentIdInOrderBySeq(Collection<UUID> recruitmentIds);

    void deleteByRecruitmentId(UUID recruitmentId);
}
