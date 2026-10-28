package com.hiremate.dashboard.application;

import com.hiremate.apply.ApplicationService;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageOverview;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 다른 모듈의 공개 서비스로 채용 진행 현황을 모은다. 조회만 한다. */
@Service
public class DashboardService {

    private final RecruitService recruits;
    private final PostingService postings;
    private final ApplicationService applications;
    private final ScreeningService screening;

    public DashboardService(RecruitService recruits, PostingService postings, ApplicationService applications,
            ScreeningService screening) {
        this.recruits = recruits;
        this.postings = postings;
        this.applications = applications;
        this.screening = screening;
    }

    @Transactional(readOnly = true)
    public DashboardView dashboard(UUID companyId, RecruitmentStatus status, String query) {
        List<RecruitmentInfo> all = recruits.list(companyId);
        String keyword = query == null ? "" : query.trim().toLowerCase(Locale.ROOT);
        List<RecruitmentInfo> searched = all.stream()
                .filter(recruitment -> recruitment.title().toLowerCase(Locale.ROOT).contains(keyword))
                .toList();
        DashboardView.StatusCounts counts = new DashboardView.StatusCounts(searched.size(),
                count(searched, RecruitmentStatus.DRAFT), count(searched, RecruitmentStatus.PUBLISHED),
                count(searched, RecruitmentStatus.IN_PROGRESS), count(searched, RecruitmentStatus.CLOSED));
        List<DashboardView.RecruitmentCard> items = searched.stream()
                .filter(recruitment -> status == null || recruitment.status() == status)
                .map(recruitment -> card(companyId, recruitment))
                .toList();
        return new DashboardView(counts, items);
    }

    private DashboardView.RecruitmentCard card(UUID companyId, RecruitmentInfo recruitment) {
        PostingView posting = postings.view(companyId, recruitment.id());
        Map<UUID, StageOverview.DecisionCounts> stageCounts = screening.stageCounts(companyId, recruitment.id());
        List<DashboardView.DashboardStep> steps = recruitment.stages().stream()
                .map(stage -> new DashboardView.DashboardStep(stage.id(), stage.name(), stage.type(), stage.status(),
                        stageCounts.containsKey(stage.id()) ? stageCounts.get(stage.id()).total() : null, stage.icon()))
                .toList();
        return new DashboardView.RecruitmentCard(recruitment.id(), posting.postingId(), recruitment.title(),
                recruitment.status(), applications.count(companyId, recruitment.id()), posting.closeAt(),
                recruitment.currentStageId(), steps, recruitment.createdAt());
    }

    private static long count(List<RecruitmentInfo> recruitments, RecruitmentStatus status) {
        return recruitments.stream().filter(recruitment -> recruitment.status() == status).count();
    }
}
