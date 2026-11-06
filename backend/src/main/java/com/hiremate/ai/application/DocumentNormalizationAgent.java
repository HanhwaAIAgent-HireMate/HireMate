package com.hiremate.ai.application;

import com.hiremate.apply.DocumentNormalizationRequest;

/** 지원 문서 정리를 현재 Application Agent 설정에 따라 맡긴다. */
public interface DocumentNormalizationAgent {
    void normalize(DocumentNormalizationRequest request);
}
