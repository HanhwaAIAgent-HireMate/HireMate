package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PostingCriteriaAgent;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.posting.ScreeningRubric.CriterionType;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/**
 * 개발용 서류 평가 기준 초안. 항목 문장의 낱말로 유형을 고르고, 문장 그대로 서류에서 확인하는 판정 기준을 쓴다.
 * '중요'는 목록이 둘 이상이고 주요 업무가 있으면 첫 항목을 첫 주요 업무로 추천한다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.STUB)
class StubPostingCriteriaAgent implements PostingCriteriaAgent {

    private static final Pattern CONDITION = Pattern.compile("\\d+\\s*년|자격증|학위|전공");
    private static final Pattern COMPOSITE = Pattern.compile("와 |과 | 및 |,");

    @Override
    public CriterionDraft draftCriterion(PostingContent posting, ScreeningRubric.Category category, String text,
            String ncsUnitCode) {
        CriterionType type = CONDITION.matcher(text).find() ? CriterionType.CONDITION
                : COMPOSITE.matcher(text).find() ? CriterionType.COMPOSITE : CriterionType.SINGLE;
        String partial = type == CriterionType.COMPOSITE ? "서류에서 '" + text + "' 중 일부만 확인된다" : null;
        return new CriterionDraft(type, "서류에서 '" + text + "'을 확인할 수 있다", partial,
                "서류에서 '" + text + "'이 확인되지 않는다", List.of());
    }

    @Override
    public ImportantAdvice recommendImportant(PostingContent posting) {
        return new ImportantAdvice(first(posting.qualifications(), posting.duties()),
                first(posting.preferred(), posting.duties()));
    }

    private static List<ImportantItem> first(List<String> items, List<String> duties) {
        return items.size() < 2 || duties.isEmpty() ? List.of() : List.of(new ImportantItem(0, duties.getFirst()));
    }
}
