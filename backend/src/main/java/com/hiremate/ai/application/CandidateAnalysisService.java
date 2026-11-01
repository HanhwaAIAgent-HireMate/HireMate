package com.hiremate.ai.application;

import com.hiremate.apply.ApplicationService;
import com.hiremate.company.CompanyService;
import com.hiremate.company.Talent;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.ScreeningRubric;
import com.hiremate.screening.ScreeningService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CandidateAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(CandidateAnalysisService.class);

    private final ScreeningService screening;
    private final ApplicationService applications;
    private final PostingService postings;
    private final CompanyService companies;
    private final CandidateAnalyst analyst;
    private final ProfileReader profiles;

    public CandidateAnalysisService(ScreeningService screening, ApplicationService applications,
            PostingService postings, CompanyService companies, CandidateAnalyst analyst, ProfileReader profiles) {
        this.screening = screening;
        this.applications = applications;
        this.postings = postings;
        this.companies = companies;
        this.analyst = analyst;
        this.profiles = profiles;
    }

    /** 현재 전형의 대상 지원자만 분석한다. */
    public CandidateAnalysis analyze(UUID companyId, UUID stageId, UUID applicationId) {
        screening.detail(companyId, stageId, applicationId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        return analyst.analyze(applications.detail(companyId, applicationId),
                postings.draftContext(companyId, recruitmentId).content(),
                postings.screeningRubric(companyId, recruitmentId));
    }

    /** 현재 전형의 대상 지원자만 프로필을 읽는다. 분석 Agent들이 쌓은 항목을 확인 상태와 함께 돌려준다. */
    public CandidateProfileView profile(UUID companyId, UUID stageId, UUID applicationId) {
        screening.detail(companyId, stageId, applicationId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        return profiles.read(companyId, recruitmentId, applicationId);
    }

    /**
     * 표 보기의 열: 자격요건, 우대사항, 회사 인재상(설정의 인재상 + 회사 소개 · 조직 문화 글에서 뽑은 요소) 순서. 평가 기준 열은 지원자 카드의 항목 판정과 같은 ID를 쓰고,
     * 인재상 열은 설정 순서로 ID를 만든다. 열 이름은 짧은 키워드이고, 만들지 못하면 원래 문장을 그대로 쓴다.
     */
    public CandidateTable table(UUID companyId, UUID stageId) {
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        List<ScreeningRubric.Criterion> criteria = postings.screeningRubric(companyId, recruitmentId).criteria()
                .stream().sorted(Comparator.comparing(ScreeningRubric.Criterion::category)).toList();
        List<Talent> talents = companies.factors(companyId);
        List<String> texts = new ArrayList<>(criteria.stream().map(ScreeningRubric.Criterion::text).toList());
        talents.forEach(talent -> texts.add(talent.title()));
        List<String> labels = labels(texts);
        List<CandidateTable.Feature> features = new ArrayList<>();
        for (int index = 0; index < criteria.size(); index++) {
            ScreeningRubric.Criterion criterion = criteria.get(index);
            features.add(new CandidateTable.Feature(criterion.criterionId(),
                    criterion.category() == ScreeningRubric.Category.QUALIFICATION ? CandidateTable.Group.QUALIFICATION
                            : CandidateTable.Group.PREFERENCE,
                    criterion.criterionType() == ScreeningRubric.CriterionType.CONDITION ? CandidateTable.Kind.CONDITION
                            : CandidateTable.Kind.EXPERIENCE,
                    labels.get(index), criterion.text()));
        }
        for (int index = 0; index < talents.size(); index++) {
            Talent talent = talents.get(index);
            String text = talent.description().isBlank() ? talent.title()
                    : talent.title() + " - " + talent.description();
            features.add(new CandidateTable.Feature("T-" + (index + 1), CandidateTable.Group.TALENT,
                    CandidateTable.Kind.EXPERIENCE, labels.get(criteria.size() + index), text));
        }
        return new CandidateTable(features);
    }

    /**
     * 현재 전형의 대상 지원자가 회사 인재상마다 맞는 정도. 설정의 인재상과 같은 순서다.
     * 상으로 판정한 인재상은 전체 지원자의 인재상 포함 정렬에 쓰도록 남긴다.
     */
    public TalentFit talents(UUID companyId, UUID stageId, UUID applicationId) {
        screening.detail(companyId, stageId, applicationId);
        UUID recruitmentId = screening.overview(companyId, stageId).recruitmentId();
        return judge(companyId, recruitmentId, applicationId, companies.factors(companyId));
    }

    /** 분석이 끝난 지원자의 인재상을 판정해 둔다. 인재상이 없으면 판정하지 않는다. */
    public void judgeTalents(UUID applicationId) {
        UUID companyId = applications.companyOf(applicationId);
        List<Talent> talents = companies.factors(companyId);
        if (!talents.isEmpty()) {
            judge(companyId, applications.detail(companyId, applicationId).info().recruitmentId(), applicationId,
                    talents);
        }
    }

    /** 개발용 응답은 판정하지 않았으므로 남기지 않는다. */
    private TalentFit judge(UUID companyId, UUID recruitmentId, UUID applicationId, List<Talent> talents) {
        TalentFit fit = analyst.talents(new TalentFitRequest(companyId, recruitmentId, applicationId, talents));
        if (!fit.stub()) {
            applications.recordTalents(applicationId, fit.items().stream()
                    .filter(item -> item.level() == TalentFit.Level.HIGH)
                    .map(TalentFit.Match::title)
                    .toList());
        }
        return fit;
    }

    private List<String> labels(List<String> texts) {
        if (texts.isEmpty()) {
            return List.of();
        }
        try {
            List<String> labels = analyst.labels(texts).labels();
            if (labels.size() == texts.size()) {
                return labels;
            }
            log.warn("Feature labels came back with {} of {} texts", labels.size(), texts.size());
        } catch (RuntimeException unavailable) {
            log.warn("Could not make feature labels", unavailable);
        }
        return texts;
    }
}
