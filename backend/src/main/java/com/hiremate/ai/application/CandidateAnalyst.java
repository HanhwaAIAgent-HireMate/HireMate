package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDetail;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import java.util.List;

/** 특정 지원자의 제출 자료를 공고 조건과 맞춰 본다 (Application Agent). */
public interface CandidateAnalyst {

    CandidateAnalysis analyze(ApplicantDetail applicant, PostingContent posting, ScreeningRubric rubric);

    /** 표 보기의 열 이름. 평가 기준 · 인재상 문장을 같은 순서의 짧은 키워드로 바꾼다. */
    FeatureLabels labels(List<String> texts);

    /** 지원자 한 명이 회사 인재상마다 맞는 정도. 지원 접수 때 저장한 분석만 근거로 쓴다. */
    TalentFit talents(TalentFitRequest request);

    /** 회사 소개 · 조직 문화 글에서 회사가 사람을 볼 때 중요하게 여기는 요소를 뽑는다. */
    CompanyFactors factors(String text);
}
