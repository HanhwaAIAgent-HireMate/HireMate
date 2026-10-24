package com.hiremate.ai.api;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalysisService;
import com.hiremate.ai.application.CandidateProfileView;
import com.hiremate.global.AuthenticatedMember;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** 지원자 카드의 AI 분석 요약과 프로필 탭 (STG-06). */
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

    /** 분석 Agent들이 쌓은 프로필 항목과 확인 상태. 이름이 회사 프로필(profile)과 겹치지 않게 candidateProfile이다. */
    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/profile")
    public CandidateProfileView candidateProfile(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return service.profile(member.companyId(), stageId, applicationId);
    }
}
