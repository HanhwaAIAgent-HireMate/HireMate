package com.hiremate.recruit.domain;

import jakarta.persistence.LockModeType;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

public interface StageRepository extends JpaRepository<Stage, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from Stage s where s.id = :stageId")
    Optional<Stage> lock(UUID stageId);

    List<Stage> findByRecruitmentIdOrderBySeq(UUID recruitmentId);

    List<Stage> findByRecruitmentIdInOrderBySeq(Collection<UUID> recruitmentIds);

    void deleteByRecruitmentId(UUID recruitmentId);
}
