package com.hiremate.ai.api;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalysisService;
import com.hiremate.global.AuthenticatedMember;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** 지원자 카드의 AI 분석 요약 (STG-06). */
@RestController
public class CandidateAnalysisController {

    private final CandidateAnalysisService service;

    public CandidateAnalysisController(CandidateAnalysisService service) {
        this.service = service;
    }

    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/analysis")
    public CandidateAnalysis analysis(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return service.analyze(member.companyId(), stageId, applicationId);
    }
}
