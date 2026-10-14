package com.hiremate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.company.CompanyService;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class FileServiceTests extends IntegrationTest {

    @Autowired
    private FileService files;

    @Autowired
    private CompanyService companies;

    @Test
    @DisplayName("저장한 파일을 같은 기업에서 다시 읽는다")
    void storesAndReadsFileWithinCompany() {
        UUID companyId = companies.createCompany("파일 기업").companyId();
        byte[] content = "%PDF-1.4 test".getBytes(StandardCharsets.UTF_8);

        StoredFileInfo stored = files.store(companyId, "이력서.pdf", "application/pdf", content);
        FileContent read = files.read(companyId, stored.fileId());

        assertThat(read.bytes()).isEqualTo(content);
        assertThat(read.info().originalName()).isEqualTo("이력서.pdf");
        assertThat(read.info().size()).isEqualTo(content.length);
    }

    @Test
    @DisplayName("다른 기업의 파일은 찾지 못한다")
    void hidesFilesOfOtherCompanies() {
        UUID owner = companies.createCompany("소유 기업").companyId();
        UUID other = companies.createCompany("다른 기업").companyId();
        StoredFileInfo stored = files.store(owner, "a.pdf", "application/pdf", new byte[] {1});

        assertThatThrownBy(() -> files.read(other, stored.fileId()))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.code()).isEqualTo("FILE_NOT_FOUND"));
    }
}
