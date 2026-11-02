package com.hiremate.interview;

import com.hiremate.global.ApiException;
import com.hiremate.interview.domain.InterviewSession;
import com.hiremate.interview.domain.InterviewSessionRepository;
import com.hiremate.interview.domain.InterviewSharedNote;
import com.hiremate.interview.domain.InterviewSharedNoteRepository;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.StageStatus;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** HR과 배정된 면접관에게 공개하는 기록. 개인 메모나 추천 의견은 복사하지 않는다. */
@Service
public class InterviewSharedNotes {
    private final InterviewSharedNoteRepository notes;
    private final InterviewSessionRepository sessions;
    private final RecruitService recruits;
    private final ApplicationEventPublisher events;

    public InterviewSharedNotes(InterviewSharedNoteRepository notes, InterviewSessionRepository sessions,
            RecruitService recruits, ApplicationEventPublisher events) {
        this.notes = notes;
        this.sessions = sessions;
        this.recruits = recruits;
        this.events = events;
    }

    @Transactional(readOnly = true)
    public List<Note> read(UUID companyId, UUID stageId, UUID applicationId, UUID viewer, boolean interviewer) {
        recruits.getByStage(companyId, stageId);
        if (interviewer) {
            assigned(session(companyId, stageId, applicationId), viewer);
        }
        return notes.findByStageIdAndApplicationIdAndCompanyIdOrderByUpdatedAtAsc(stageId, applicationId, companyId)
                .stream().map(note -> view(note, viewer)).toList();
    }

    @Transactional
    public Note save(UUID companyId, UUID stageId, UUID applicationId, UUID memberId, String name,
            String text, long expectedVersion) {
        InterviewSession session = sessions.lock(companyId, stageId, applicationId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "INTERVIEW_SESSION_NOT_FOUND", "No interview."));
        InterviewerRole role = assigned(session, memberId);
        StageStatus stageStatus = recruits.getByStage(companyId, stageId).stage(stageId).orElseThrow().status();
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS || stageStatus != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "Interview is not running.");
        }
        InterviewSharedNote note = notes.findById(new InterviewSharedNote.Key(stageId, applicationId, memberId))
                .orElseGet(() -> new InterviewSharedNote(stageId, applicationId, memberId, companyId));
        if (note.getVersion() != expectedVersion) {
            throw new ApiException(HttpStatus.CONFLICT, "MEMO_CONFLICT", "Reload the shared note.");
        }
        note.write(name, role, text.strip());
        notes.saveAndFlush(note);
        events.publishEvent(new InterviewSessionChanged(companyId, stageId, applicationId));
        return view(note, memberId);
    }

    private InterviewSession session(UUID companyId, UUID stageId, UUID applicationId) {
        return sessions.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND,
                        "INTERVIEW_SESSION_NOT_FOUND", "No interview."));
    }

    private static InterviewerRole assigned(InterviewSession session, UUID memberId) {
        InterviewerRole role = session.roleOf(memberId);
        if (role == null) {
            throw new ApiException(HttpStatus.FORBIDDEN, "INTERVIEW_ACCESS_DENIED", "Not assigned.");
        }
        return role;
    }

    private static Note view(InterviewSharedNote note, UUID viewer) {
        return new Note(note.getMemberId(), note.getMemberName(), note.getInterviewerRole(), note.getText(),
                note.getVersion(), note.getUpdatedAt(), note.getMemberId().equals(viewer));
    }

    public record Note(UUID memberId, String name, InterviewerRole role, String text,
            long version, Instant updatedAt, boolean mine) {
    }
}
