package com.hiremate.assessment.api;

import com.hiremate.assessment.AssessmentResultView;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.assessment.ImportResult;
import com.hiremate.assessment.TablePreview;
import com.hiremate.file.FileContent;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 평가 결과 등록 (STG-10). */
@RestController
@RequestMapping("/api/stages/{stageId}/assessment")
public class AssessmentController {

    private final AssessmentService assessments;

    public AssessmentController(AssessmentService assessments) {
        this.assessments = assessments;
    }

    /** 결과표(CSV · XLSX)를 읽어 열과 행을 돌려준다. 저장하지 않는다. */
    @PostMapping(path = "/preview", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public TablePreview preview(AuthenticatedMember member, @PathVariable UUID stageId,
            @RequestPart("file") MultipartFile file) throws IOException {
        return assessments.preview(file.getOriginalFilename(), file.getBytes());
    }

    @PostMapping("/import")
    public ImportResult importResults(AuthenticatedMember member, @PathVariable UUID stageId,
            @RequestParam(defaultValue = "false") boolean dryRun, @Valid @RequestBody ImportRequest request) {
        return assessments.importResults(member.companyId(), stageId, request.identifierType(),
                request.entries().stream().map(ImportRow::toEntry).toList(), dryRun);
    }

    @GetMapping("/results/{applicationId}")
    public ResponseEntity<AssessmentResultView> result(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        return assessments.find(member.companyId(), stageId, applicationId)
                .map(ResponseEntity::ok)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "RESULT_NOT_FOUND", "No result yet."));
    }

    @PutMapping("/results/{applicationId}")
    public AssessmentResultView save(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @Valid @RequestBody ManualResultRequest request) {
        return assessments.saveManual(member.companyId(), stageId, applicationId, request.total(), request.areas(),
                request.grade(), request.url(), request.note());
    }

    @PostMapping(path = "/results/{applicationId}/file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public AssessmentResultView attach(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId, @RequestPart("file") MultipartFile file) throws IOException {
        return assessments.attach(member.companyId(), stageId, applicationId, file.getOriginalFilename(),
                file.getBytes());
    }

    @GetMapping("/results/{applicationId}/file")
    public ResponseEntity<byte[]> file(AuthenticatedMember member, @PathVariable UUID stageId,
            @PathVariable UUID applicationId) {
        FileContent content = assessments.file(member.companyId(), stageId, applicationId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline()
                        .filename(content.info().originalName(), StandardCharsets.UTF_8).build().toString())
                .body(content.bytes());
    }

    public record ImportRequest(@NotNull AssessmentService.IdentifierType identifierType,
            @NotEmpty @Size(max = 2000) List<@Valid ImportRow> entries) {
    }

    public record ImportRow(@NotNull @Size(max = 254) String identifier,
            @Schema(nullable = true) UUID applicationId,
            @Schema(nullable = true) @DecimalMin("0") @DecimalMax("1000") BigDecimal total,
            @NotNull Map<String, BigDecimal> areas, @Schema(nullable = true) @Size(max = 20) String grade) {

        AssessmentService.ResultEntry toEntry() {
            return new AssessmentService.ResultEntry(identifier, applicationId, total, areas, grade);
        }
    }

    public record ManualResultRequest(@Schema(nullable = true) @DecimalMin("0") @DecimalMax("1000") BigDecimal total,
            @NotNull Map<String, BigDecimal> areas, @Schema(nullable = true) @Size(max = 20) String grade,
            @Schema(nullable = true) @Size(max = 500) String url,
            @Schema(nullable = true) @Size(max = 2000) String note) {
    }
}
