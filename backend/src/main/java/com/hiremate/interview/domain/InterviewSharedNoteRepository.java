package com.hiremate.interview.domain;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InterviewSharedNoteRepository extends JpaRepository<InterviewSharedNote, InterviewSharedNote.Key> {
    List<InterviewSharedNote> findByStageIdAndApplicationIdAndCompanyIdOrderByUpdatedAtAsc(
            UUID stageId, UUID applicationId, UUID companyId);
}
