package com.hiremate.company.api;

import com.hiremate.company.CompanyLogoService;
import com.hiremate.file.FileContent;
import com.hiremate.global.AuthenticatedMember;
import java.io.IOException;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 회사 로고 (설정 › 회사 소개). 안내 메일과 공고 포스터에 같이 쓴다. */
@RestController
@RequestMapping("/api/companies/me/logo")
public class CompanyLogoController {

    private final CompanyLogoService logos;

    public CompanyLogoController(CompanyLogoService logos) {
        this.logos = logos;
    }

    /** PNG · JPEG, 5MB까지 받는다. 메일과 포스터에 맞게 줄여 저장한다. */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void upload(AuthenticatedMember member, @RequestPart("file") MultipartFile file) throws IOException {
        logos.upload(member.companyId(), file.getOriginalFilename(), file.getBytes());
    }

    @DeleteMapping
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(AuthenticatedMember member) {
        logos.delete(member.companyId());
    }

    /** 설정 화면에 보여 줄 로고 그림. 새로 올리면 바뀌어 저장해 두지 않게 한다. */
    @GetMapping
    public ResponseEntity<byte[]> logo(AuthenticatedMember member) {
        FileContent image = logos.logo(member.companyId());
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(image.info().contentType()))
                .cacheControl(CacheControl.noStore()).body(image.bytes());
    }
}
