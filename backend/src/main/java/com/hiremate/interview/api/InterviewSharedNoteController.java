package com.hiremate.interview.api;

import com.hiremate.global.AuthenticatedMember;
import com.hiremate.interview.InterviewSharedNotes;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 개인 메모와 별도의 공유 기록. HR은 조회만, 배정된 면접관은 본인 기록만 수정한다. */
@RestController
public class InterviewSharedNoteController {
    private final InterviewSharedNotes notes;

    public InterviewSharedNoteController(InterviewSharedNotes notes) {
        this.notes = notes;
    }

    @GetMapping("/api/interviewer/sessions/{stageId}/{applicationId}/shared-notes")
    public List<InterviewSharedNotes.Note> mine(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return notes.read(member.companyId(), stageId, applicationId, member.memberId(), true);
    }

    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/interview/shared-notes")
    public List<InterviewSharedNotes.Note> hr(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return notes.read(member.companyId(), stageId, applicationId, member.memberId(), false);
    }

    @PutMapping("/api/interviewer/sessions/{stageId}/{applicationId}/shared-notes/me")
    public InterviewSharedNotes.Note save(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody SharedNoteRequest request) {
        return notes.save(member.companyId(), stageId, applicationId, member.memberId(), member.name(),
                request.text(), request.expectedVersion());
    }

    public record SharedNoteRequest(@NotNull @Size(max = 10000) String text,
            @NotNull @PositiveOrZero Long expectedVersion) {
    }
}
