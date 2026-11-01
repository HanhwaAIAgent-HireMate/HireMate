package com.hiremate.ai.api;

import com.hiremate.ai.application.CandidateAnalysis;
import com.hiremate.ai.application.CandidateAnalysisService;
import com.hiremate.ai.application.CandidateProfileView;
import com.hiremate.ai.application.CandidateTable;
import com.hiremate.ai.application.TalentFit;
import com.hiremate.global.AuthenticatedMember;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

/** 지원자 카드의 AI 분석 요약과 프로필 탭 (STG-06), 선택 지원자 표 보기의 열과 인재상 판정. */
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

    /** 표 보기의 열. 칸은 지원자마다 analysis(평가 기준)와 talents(인재상)로 채운다. */
    @GetMapping("/api/stages/{stageId}/table")
    public CandidateTable table(AuthenticatedMember member, @PathVariable UUID stageId) {
        return service.table(member.companyId(), stageId);
    }

    /** 지원자 한 명의 인재상 판정. 처음 부르면 Application Agent가 판정하고, 그 뒤로는 저장된 판정을 돌려준다. */
    @GetMapping("/api/stages/{stageId}/candidates/{applicationId}/talents")
    public TalentFit talents(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return service.talents(member.companyId(), stageId, applicationId);
    }
}
