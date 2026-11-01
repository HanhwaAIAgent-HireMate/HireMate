package com.hiremate.interview;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/** 면접 전형에 지정한 면접관. 담당(인사 · 실무) 순서대로, 지정한 계정만 들어 있다. */
public record StageInterviewers(List<Slot> slots) {

    @Schema(name = "InterviewerSlot")
    public record Slot(InterviewerRole role, UUID memberId, String name) {
    }
}
