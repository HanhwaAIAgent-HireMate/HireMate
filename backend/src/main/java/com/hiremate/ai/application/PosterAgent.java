package com.hiremate.ai.application;

import com.hiremate.company.CanvaConnectionService.CanvaRegion;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterProposal;
import java.util.List;

/** 공고 디자인 화면의 Root가 공고 Agent를 호출해 만든 추천/수정안. */
public interface PosterAgent {
    PosterProposal design(PosterContext context, String request);

    default CanvaMapping mapCanva(List<CanvaRegion> regions) {
        throw new com.hiremate.global.ApiException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
                "CANVA_MODEL_REQUIRED", "Canva 디자인을 가져오려면 실제 모델 연결이 필요해요.");
    }

    record CanvaMapping(List<CanvaBinding> bindings) {
    }

    default TemplateLayout templateLayout(List<LayoutRegion> regions) {
        throw new com.hiremate.global.ApiException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE,
                "POSTER_MODEL_REQUIRED", "원본 구성을 해석하려면 실제 모델 연결이 필요해요.");
    }

    record LayoutRegion(String id, String text, double left, double top, double width, double height, String kind) {
    }

    record LayoutSection(String binding, List<Integer> elements, Integer heading, int body) {
    }

    record TemplateLayout(List<LayoutSection> sections) {
    }

    record CanvaBinding(String elementId, String binding) {
    }
}
