package com.hiremate.company.api;

import com.hiremate.company.CompanyService;
import com.hiremate.company.PosterBrand;
import com.hiremate.company.PosterBrandService;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/companies/me/poster-brand")
public class PosterBrandController {

    private final CompanyService companies;
    private final PosterBrandService brands;

    public PosterBrandController(CompanyService companies, PosterBrandService brands) {
        this.companies = companies;
        this.brands = brands;
    }

    @GetMapping
    public PosterBrand get(AuthenticatedMember member) {
        return companies.posterBrand(member.companyId());
    }

    @PutMapping
    public PosterBrand update(AuthenticatedMember member, @Valid @RequestBody PosterBrandRequest request) {
        PosterBrand old = companies.posterBrand(member.companyId());
        return companies.updatePosterBrand(member.companyId(), new PosterBrand(request.template(), request.mood(),
                request.color(), request.decoration(), old.logoFileId(), old.templates()));
    }

    @PostMapping("/templates")
    public PosterBrand addTemplate(AuthenticatedMember member, @Valid @RequestBody PosterTemplateRequest request) {
        return companies.addPosterTemplate(member.companyId(), request.name(), request.template(), request.color(),
                request.canvasJson());
    }

    @GetMapping("/logo")
    public ResponseEntity<byte[]> logo(AuthenticatedMember member) {
        FileContent file = brands.logo(member.companyId());
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(file.info().contentType()))
                .cacheControl(CacheControl.noStore()).body(file.bytes());
    }

    @DeleteMapping("/templates/{templateId}")
    public PosterBrand deleteTemplate(AuthenticatedMember member, @PathVariable UUID templateId) {
        return companies.deletePosterTemplate(member.companyId(), templateId);
    }

    public record PosterBrandRequest(
            @NotNull @Pattern(regexp = "CLASSIC|EDITORIAL|BOLD|PREMIUM|NATURAL|TICKET") String template,
            @NotNull @Pattern(regexp = "TRUST|CLEAR|WARM|PREMIUM|LIVELY|NATURAL") String mood,
            @NotNull @Pattern(regexp = "^#[0-9a-fA-F]{6}$") String color,
            @Min(0) @Max(2) int decoration) {
    }

    public record PosterTemplateRequest(@NotBlank @Size(max = 60) String name,
            @NotNull @Pattern(regexp = "CLASSIC|EDITORIAL|BOLD|PREMIUM|NATURAL|TICKET") String template,
            @NotNull @Pattern(regexp = "^#[0-9a-fA-F]{6}$") String color,
            @Schema(nullable = true) @Size(max = 200000) String canvasJson) {
    }
}
