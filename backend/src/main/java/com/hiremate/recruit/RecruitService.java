package com.hiremate.recruit;

import com.hiremate.global.ApiException;
import com.hiremate.recruit.domain.Recruitment;
import com.hiremate.recruit.domain.RecruitmentRepository;
import com.hiremate.recruit.domain.Stage;
import com.hiremate.recruit.domain.StageRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 채용과 전형 구성, 진행 상태. 모든 조회와 변경은 기업 범위 안에서만 한다. */
@Service
public class RecruitService {

    private final RecruitmentRepository recruitments;
    private final StageRepository stages;
    private final ApplicationEventPublisher events;

    public RecruitService(RecruitmentRepository recruitments, StageRepository stages,
            ApplicationEventPublisher events) {
        this.recruitments = recruitments;
        this.stages = stages;
        this.events = events;
    }

    @Transactional
    public RecruitmentInfo create(UUID companyId, String title, List<StageDraft> plan) {
        Recruitment recruitment = recruitments.save(new Recruitment(companyId, title));
        saveStages(recruitment.getId(), plan);
        return toInfo(recruitment);
    }

    @Transactional(readOnly = true)
    public RecruitmentInfo get(UUID companyId, UUID recruitmentId) {
        return toInfo(recruitment(companyId, recruitmentId));
    }

    /** 최근에 만든 채용부터. */
    @Transactional(readOnly = true)
    public List<RecruitmentInfo> list(UUID companyId) {
        List<Recruitment> found = recruitments.findByCompanyIdOrderByCreatedAtDesc(companyId);
        Map<UUID, List<StageInfo>> stagesByRecruitment = stages
                .findByRecruitmentIdInOrderBySeq(found.stream().map(Recruitment::getId).toList()).stream()
                .map(RecruitService::toInfo)
                .collect(Collectors.groupingBy(StageInfo::recruitmentId));
        return found.stream()
                .map(recruitment -> toInfo(recruitment,
                        stagesByRecruitment.getOrDefault(recruitment.getId(), List.of())))
                .toList();
    }

    /** 전형이 속한 채용. 다른 기업의 전형이면 404다. */
    @Transactional(readOnly = true)
    public RecruitmentInfo getByStage(UUID companyId, UUID stageId) {
        Stage stage = stages.findById(stageId).orElseThrow(RecruitService::stageNotFound);
        return recruitments.findByIdAndCompanyId(stage.getRecruitmentId(), companyId)
                .map(this::toInfo)
                .orElseThrow(RecruitService::stageNotFound);
    }

    @Transactional
    public void rename(UUID companyId, UUID recruitmentId, String title) {
        recruitment(companyId, recruitmentId).rename(title);
    }

    /** 게시 전에만 전형 구성을 바꿀 수 있다 (OI-01 MVP 기본값). */
    @Transactional
    public RecruitmentInfo replaceStages(UUID companyId, UUID recruitmentId, List<StageDraft> plan) {
        Recruitment recruitment = recruitment(companyId, recruitmentId);
        requireStatus(recruitment, RecruitmentStatus.DRAFT, "RECRUITMENT_LOCKED");
        stages.deleteByRecruitmentId(recruitmentId);
        stages.flush();
        saveStages(recruitmentId, plan);
        return toInfo(recruitment);
    }

    @Transactional
    public RecruitmentInfo publish(UUID companyId, UUID recruitmentId) {
        Recruitment recruitment = recruitment(companyId, recruitmentId);
        requireStatus(recruitment, RecruitmentStatus.DRAFT, "RECRUITMENT_ALREADY_PUBLISHED");
        if (stages.findByRecruitmentIdOrderBySeq(recruitmentId).isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGES_REQUIRED", "At least one stage is required.");
        }
        recruitment.publish();
        return toInfo(recruitment);
    }

    /** 공고가 마감되면 첫 전형을 시작한다. 이미 시작했으면 아무것도 하지 않는다. */
    @Transactional
    public Optional<StageInfo> startFirstStage(UUID companyId, UUID recruitmentId) {
        Recruitment recruitment = recruitment(companyId, recruitmentId);
        if (recruitment.getStatus() != RecruitmentStatus.PUBLISHED) {
            return Optional.empty();
        }
        Stage first = stages.findByRecruitmentIdOrderBySeq(recruitmentId).getFirst();
        first.activate();
        recruitment.moveTo(first.getId());
        return Optional.of(toInfo(first));
    }

    /** 진행 중인 전형의 결과를 확정한다. */
    @Transactional
    public StageInfo confirmStage(UUID companyId, UUID stageId, UUID memberId) {
        Stage stage = stage(companyId, stageId);
        if (stage.getStatus() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The stage is not in progress.");
        }
        stage.confirm(memberId);
        return toInfo(stage);
    }

    /**
     * 확정한 전형을 종료하고 다음 전형을 시작한다. 다음 전형이 없으면 채용을 종료하고 빈 값을 돌려준다.
     */
    @Transactional
    public Optional<StageInfo> finishStage(UUID companyId, UUID stageId) {
        Stage stage = stage(companyId, stageId);
        if (stage.getStatus() != StageStatus.CONFIRMED) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_CONFIRMED", "Confirm the stage results first.");
        }
        stage.finish();
        Recruitment recruitment = recruitment(companyId, stage.getRecruitmentId());
        Optional<Stage> next = stages.findByRecruitmentIdOrderBySeq(stage.getRecruitmentId()).stream()
                .filter(candidate -> candidate.getSeq() > stage.getSeq())
                .findFirst();
        if (next.isEmpty()) {
            recruitment.close();
            events.publishEvent(new RecruitmentClosed(recruitment.getId(), companyId));
            return Optional.empty();
        }
        next.get().activate();
        recruitment.moveTo(next.get().getId());
        return Optional.of(toInfo(next.get()));
    }

    private void saveStages(UUID recruitmentId, List<StageDraft> plan) {
        List<Stage> created = new ArrayList<>();
        for (int i = 0; i < plan.size(); i++) {
            created.add(new Stage(recruitmentId, i + 1, plan.get(i).name(), plan.get(i).type()));
        }
        stages.saveAll(created);
    }

    private Stage stage(UUID companyId, UUID stageId) {
        Stage stage = stages.findById(stageId).orElseThrow(RecruitService::stageNotFound);
        recruitments.findByIdAndCompanyId(stage.getRecruitmentId(), companyId)
                .orElseThrow(RecruitService::stageNotFound);
        return stage;
    }

    private Recruitment recruitment(UUID companyId, UUID recruitmentId) {
        return recruitments.findByIdAndCompanyId(recruitmentId, companyId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "RECRUITMENT_NOT_FOUND", "Recruitment not found."));
    }

    private static void requireStatus(Recruitment recruitment, RecruitmentStatus status, String code) {
        if (recruitment.getStatus() != status) {
            throw new ApiException(HttpStatus.CONFLICT, code, "The recruitment cannot be changed in this status.");
        }
    }

    private static ApiException stageNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "STAGE_NOT_FOUND", "Stage not found.");
    }

    private RecruitmentInfo toInfo(Recruitment recruitment) {
        return toInfo(recruitment, stages.findByRecruitmentIdOrderBySeq(recruitment.getId()).stream()
                .map(RecruitService::toInfo)
                .toList());
    }

    private static RecruitmentInfo toInfo(Recruitment recruitment, List<StageInfo> stageInfos) {
        return new RecruitmentInfo(recruitment.getId(), recruitment.getCompanyId(), recruitment.getTitle(),
                recruitment.getStatus(), recruitment.getCurrentStageId(), stageInfos, recruitment.getCreatedAt(),
                recruitment.getPublishedAt(), recruitment.getClosedAt());
    }

    private static StageInfo toInfo(Stage stage) {
        return new StageInfo(stage.getId(), stage.getRecruitmentId(), stage.getSeq(), stage.getName(),
                stage.getType(), stage.getStatus(), stage.getConfirmedAt(), stage.getDoneAt());
    }
}
