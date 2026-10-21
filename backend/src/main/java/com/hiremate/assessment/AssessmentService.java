package com.hiremate.assessment;

import com.hiremate.apply.ApplicantInfo;
import com.hiremate.apply.ApplicationService;
import com.hiremate.assessment.application.TableReader;
import com.hiremate.assessment.domain.AssessmentResult;
import com.hiremate.assessment.domain.AssessmentResultRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import com.hiremate.global.JsonText;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.ScreeningService;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.type.TypeReference;

/**
 * 외부 평가 결과 등록 (FR-25, FR-26). 결과표 · 지원자별 파일 · 수동 입력 · 제출 파일과 URL을 평가 전형의 결과로 관리한다.
 * 총점은 전형 화면 리스트에 붙고 점수 높은 순 정렬에 쓴다. 결과가 등록되면 AssessmentResultRecorded를 발행한다.
 */
@Service
public class AssessmentService {

    private final AssessmentResultRepository results;
    private final ScreeningService screening;
    private final RecruitService recruits;
    private final ApplicationService applications;
    private final FileService files;
    private final ApplicationEventPublisher events;

    public AssessmentService(AssessmentResultRepository results, ScreeningService screening, RecruitService recruits,
            ApplicationService applications, FileService files, ApplicationEventPublisher events) {
        this.results = results;
        this.screening = screening;
        this.recruits = recruits;
        this.applications = applications;
        this.files = files;
        this.events = events;
    }

    public TablePreview preview(String fileName, byte[] content) {
        List<List<String>> rows = TableReader.read(fileName, content);
        return new TablePreview(fileName, rows.getFirst(), rows.subList(1, rows.size()));
    }

    /** 결과표 행을 이메일이나 지원번호로 지원자에 맞춘다. dryRun이면 저장하지 않고 매칭만 확인한다. */
    @Transactional
    public ImportResult importResults(UUID companyId, UUID stageId, IdentifierType type, List<ResultEntry> entries,
            boolean dryRun) {
        Stage stage = assessmentStage(companyId, stageId, !dryRun);
        Map<String, UUID> keys = keys(companyId, stage, type);
        Map<String, UUID> matches = new LinkedHashMap<>();
        List<String> unmatched = new ArrayList<>();
        for (ResultEntry entry : entries) {
            UUID applicationId = entry.applicationId() != null && keys.containsValue(entry.applicationId())
                    ? entry.applicationId() : keys.get(normalize(type, entry.identifier()));
            if (applicationId == null) {
                unmatched.add(entry.identifier());
                continue;
            }
            matches.put(entry.identifier(), applicationId);
            if (!dryRun) {
                result(companyId, stageId, applicationId)
                        .record(entry.total(), JsonText.write(entry.areas()), blankToNull(entry.grade()), "TABLE");
                screening.recordScore(companyId, stageId, applicationId, entry.total());
                recorded(companyId, stage, applicationId);
            }
        }
        return new ImportResult(matches.size(), entries.size(), matches, unmatched, !dryRun);
    }

    /** 지원자별 결과 수동 입력 (점수 · 등급 · 과제 URL). */
    @Transactional
    public AssessmentResultView saveManual(UUID companyId, UUID stageId, UUID applicationId, BigDecimal total,
            Map<String, BigDecimal> areas, String grade, String url, String note) {
        Stage stage = assessmentStage(companyId, stageId, true);
        screening.detail(companyId, stageId, applicationId);
        AssessmentResult result = result(companyId, stageId, applicationId);
        result.record(total, JsonText.write(areas), blankToNull(grade), "MANUAL");
        result.submission(blankToNull(url), blankToNull(note));
        screening.recordScore(companyId, stageId, applicationId, total);
        recorded(companyId, stage, applicationId);
        return toView(result);
    }

    /** 지원자별 결과 리포트나 과제 제출 파일(PDF). */
    @Transactional
    public AssessmentResultView attach(UUID companyId, UUID stageId, UUID applicationId, String fileName,
            byte[] content) {
        Stage stage = assessmentStage(companyId, stageId, true);
        screening.detail(companyId, stageId, applicationId);
        StoredFileInfo stored = files.storePdf(companyId, fileName, content);
        AssessmentResult result = result(companyId, stageId, applicationId);
        result.attach(stored.fileId(), stored.originalName());
        recorded(companyId, stage, applicationId);
        return toView(result);
    }

    @Transactional(readOnly = true)
    public Optional<AssessmentResultView> find(UUID companyId, UUID stageId, UUID applicationId) {
        return results.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .map(AssessmentService::toView);
    }

    @Transactional(readOnly = true)
    public FileContent file(UUID companyId, UUID stageId, UUID applicationId) {
        AssessmentResult result = results.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .filter(found -> found.getFileId() != null)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "FILE_NOT_FOUND", "File not found."));
        return files.read(companyId, result.getFileId());
    }

    private void recorded(UUID companyId, Stage stage, UUID applicationId) {
        events.publishEvent(
                new AssessmentResultRecorded(companyId, stage.recruitmentId(), stage.stageId(), applicationId));
    }

    private AssessmentResult result(UUID companyId, UUID stageId, UUID applicationId) {
        return results.findByStageIdAndApplicationIdAndCompanyId(stageId, applicationId, companyId)
                .orElseGet(() -> results.save(new AssessmentResult(stageId, applicationId, companyId)));
    }

    private Stage assessmentStage(UUID companyId, UUID stageId, boolean requireActive) {
        RecruitmentInfo recruitment = recruits.getByStage(companyId, stageId);
        StageInfo stage = recruitment.stage(stageId).orElseThrow();
        if (stage.type() != StageType.ASSESSMENT) {
            throw new ApiException(HttpStatus.CONFLICT, "NOT_ASSESSMENT_STAGE", "Only assessment stages have results.");
        }
        if (requireActive && stage.status() != StageStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "STAGE_NOT_ACTIVE", "The stage is not in progress.");
        }
        return new Stage(recruitment.id(), stageId);
    }

    private Map<String, UUID> keys(UUID companyId, Stage stage, IdentifierType type) {
        Set<UUID> inStage = screening.candidates(companyId, stage.stageId(), null, 0, 10_000).items().stream()
                .map(CandidateRow::applicationId)
                .collect(Collectors.toSet());
        return applications.applicants(companyId, stage.recruitmentId()).stream()
                .filter(applicant -> inStage.contains(applicant.applicationId()))
                .collect(Collectors.toMap(applicant -> key(type, applicant), ApplicantInfo::applicationId,
                        (left, right) -> left));
    }

    private static String key(IdentifierType type, ApplicantInfo applicant) {
        return type == IdentifierType.EMAIL ? applicant.email() : String.valueOf(applicant.applicationNo());
    }

    private static String normalize(IdentifierType type, String identifier) {
        String trimmed = identifier == null ? "" : identifier.trim();
        return type == IdentifierType.EMAIL ? trimmed.toLowerCase(Locale.ROOT) : trimmed.replaceFirst("\\.0+$", "");
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static AssessmentResultView toView(AssessmentResult result) {
        Map<String, BigDecimal> areas = JsonText.read(result.getAreas(),
                new TypeReference<LinkedHashMap<String, BigDecimal>>() { });
        return new AssessmentResultView(result.getApplicationId(), result.getTotal(),
                areas == null ? Map.of() : areas, result.getGrade(), result.getFileId(), result.getFileName(),
                result.getUrl(), result.getNote(), result.getSource(), result.getRegisteredAt());
    }

    /** 지원자를 맞추는 열. */
    public enum IdentifierType {
        EMAIL,
        APPLICATION_NO
    }

    /** 결과표 한 행. applicationId가 있으면 HR이 직접 연결한 행이다. */
    public record ResultEntry(String identifier, UUID applicationId, BigDecimal total,
            Map<String, BigDecimal> areas, String grade) {
    }

    private record Stage(UUID recruitmentId, UUID stageId) {
    }
}
