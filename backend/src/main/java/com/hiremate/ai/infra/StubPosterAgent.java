package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PosterAgent;
import com.hiremate.posting.PosterContext;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PosterProposal;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/** 개발 모드는 의미를 추측하지 않고 고정된 예시 두 개만 제공한다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.STUB)
class StubPosterAgent implements PosterAgent {
    @Override
    public PosterProposal design(PosterContext context, String request) {
        PosterDesign current = context.design();
        String color = context.brandColor() == null ? "#2459a6" : context.brandColor();
        return new PosterProposal("개발용 모드라 요청을 AI가 해석하지는 않아요. 확인할 수 있는 그라데이션형과 카드형 예시를 준비했어요.",
                List.of(example(current, current == null ? PosterDesign.Template.CLASSIC : current.template(),
                                current == null ? PosterDesign.Mood.TRUST : current.mood(), color,
                                "현재 레이아웃에 은은한 상단 그라데이션을 적용한 예시예요."),
                        example(current, PosterDesign.Template.NATURAL, PosterDesign.Mood.NATURAL, color,
                                "둥근 카드와 복지 타일을 사용한 디자인 예시예요.")));
    }

    private static PosterProposal.Recommendation example(PosterDesign current, PosterDesign.Template template,
            PosterDesign.Mood mood, String color, String reason) {
        return new PosterProposal.Recommendation(new PosterDesign(template, mood, color, 1, true,
                current != null && current.showLogo(), current == null ? null : current.logoFileId(),
                PosterDesign.BackgroundStyle.SOFT_GRADIENT,
                current == null ? Map.of() : current.stageIcons(),
                current == null ? List.of() : current.readableSections()), reason);
    }
}
