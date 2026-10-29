package com.hiremate.company.api;

import com.hiremate.company.MailLook;
import com.hiremate.company.MailStyle;
import com.hiremate.company.MailStyleService;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
import com.hiremate.mail.MailPreview;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.io.IOException;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 설정 화면(안내 메일)의 메일 꾸밈 API. 색, 부품, 로고, 배너는 모든 안내 메일과 접수 확인 메일에 쓴다. */
@RestController
@RequestMapping("/api/companies/me/mail-style")
public class MailStyleController {

    private final MailStyleService styles;

    public MailStyleController(MailStyleService styles) {
        this.styles = styles;
    }

    @GetMapping
    public MailStyle mailStyle(AuthenticatedMember member) {
        return styles.mailStyle(member.companyId());
    }

    @PutMapping
    public MailStyle changeLook(AuthenticatedMember member, @Valid @RequestBody MailLookRequest request) {
        return styles.changeLook(member.companyId(), request.look());
    }

    @PostMapping(path = "/logo", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public MailStyle uploadLogo(AuthenticatedMember member, @RequestPart("file") MultipartFile file)
            throws IOException {
        return styles.changeLogo(member.companyId(), file.getOriginalFilename(), file.getBytes());
    }

    @DeleteMapping("/logo")
    public MailStyle deleteLogo(AuthenticatedMember member) {
        return styles.deleteLogo(member.companyId());
    }

    /** 설정 화면에 보여 줄 로고 그림. 새로 올리면 바뀌어 저장해 두지 않게 한다. */
    @GetMapping("/logo")
    public ResponseEntity<byte[]> logo(AuthenticatedMember member) {
        return image(styles.logo(member.companyId()));
    }

    @PostMapping(path = "/banner", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public MailStyle uploadBanner(AuthenticatedMember member, @RequestPart("file") MultipartFile file)
            throws IOException {
        return styles.changeBanner(member.companyId(), file.getOriginalFilename(), file.getBytes());
    }

    @DeleteMapping("/banner")
    public MailStyle deleteBanner(AuthenticatedMember member) {
        return styles.deleteBanner(member.companyId());
    }

    /** 설정 화면에 보여 줄 배너 그림. */
    @GetMapping("/banner")
    public ResponseEntity<byte[]> banner(AuthenticatedMember member) {
        return image(styles.banner(member.companyId()));
    }

    /**
     * 고르는 중인 색과 부품으로 만든 예시 메일. color를 빼면 저장한 꾸밈이다.
     * accent를 빼면 보조 색 없이, header와 box를 빼면 얇은 색 줄 머리와 옅은 바탕 안내 상자로 그린다.
     */
    @GetMapping("/preview")
    public MailPreview preview(AuthenticatedMember member, @RequestParam(required = false) String color,
            @RequestParam(required = false) String accent, @RequestParam(required = false) Header header,
            @RequestParam(required = false) GuideBox box) {
        MailLook draft = color == null ? null
                : new MailLook(color, accent, header == null ? Header.LINE : header, box == null ? GuideBox.FILL : box);
        return styles.preview(member.companyId(), draft);
    }

    private static ResponseEntity<byte[]> image(FileContent image) {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(image.info().contentType()))
                .cacheControl(CacheControl.noStore())
                .body(image.bytes());
    }

    /**
     * 메일 색과 부품.
     *
     * @param color 대표 색. #0055A4처럼 6자리 색 코드이고 앞의 #는 빼도 된다
     * @param accent 보조 색. 없으면 null이다
     * @param header 머리 모양. 없으면 얇은 색 줄이다
     * @param box 안내 상자 모양. 없으면 옅은 바탕이다
     */
    public record MailLookRequest(@NotNull @Pattern(regexp = "^#?[0-9a-fA-F]{6}$") String color,
            @Schema(nullable = true) @Pattern(regexp = "^#?[0-9a-fA-F]{6}$") String accent,
            @Schema(nullable = true) Header header, @Schema(nullable = true) GuideBox box) {

        MailLook look() {
            return new MailLook(color, accent, header == null ? Header.LINE : header,
                    box == null ? GuideBox.FILL : box);
        }
    }
}
