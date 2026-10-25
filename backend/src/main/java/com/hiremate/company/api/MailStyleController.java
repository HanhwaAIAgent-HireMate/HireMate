package com.hiremate.company.api;

import com.hiremate.company.MailStyle;
import com.hiremate.company.MailStyleService;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.mail.MailPreview;
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

/** 설정 화면(안내 메일)의 메일 꾸밈 API. 색과 로고는 모든 안내 메일과 접수 확인 메일에 쓴다. */
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
    public MailStyle changeColor(AuthenticatedMember member, @Valid @RequestBody MailColorRequest request) {
        return styles.changeColor(member.companyId(), request.color());
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
        FileContent logo = styles.logo(member.companyId());
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(logo.info().contentType()))
                .cacheControl(CacheControl.noStore())
                .body(logo.bytes());
    }

    /** 고르는 중인 색으로 만든 예시 메일. color를 빼면 저장한 색이다. */
    @GetMapping("/preview")
    public MailPreview preview(AuthenticatedMember member, @RequestParam(required = false) String color) {
        return styles.preview(member.companyId(), color);
    }

    /**
     * 메일 색.
     *
     * @param color #0055A4처럼 6자리 색 코드. 앞의 #는 빼도 된다
     */
    public record MailColorRequest(@NotNull @Pattern(regexp = "^#?[0-9a-fA-F]{6}$") String color) {
    }
}
