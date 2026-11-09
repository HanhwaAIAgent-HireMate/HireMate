package com.hiremate.file;

import com.hiremate.file.application.FileStorage;
import com.hiremate.file.domain.StoredFile;
import com.hiremate.file.domain.StoredFileRepository;
import com.hiremate.global.ApiException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** 파일을 기업 단위로 저장하고 읽는다. 다른 기업의 파일은 찾지 못한 것으로 다룬다. */
@Service
public class FileService {

    private static final Logger LOG = LoggerFactory.getLogger(FileService.class);

    private final StoredFileRepository files;
    private final FileStorage storage;

    public FileService(StoredFileRepository files, FileStorage storage) {
        this.files = files;
        this.storage = storage;
    }

    @Transactional
    public StoredFileInfo store(UUID companyId, String originalName, String contentType, byte[] content) {
        StoredFile file = new StoredFile(companyId, originalName, contentType, content.length);
        storage.save(file.getStorageKey(), content);
        return toInfo(files.save(file));
    }

    /** 지원서 사진은 접수가 롤백되면 저장소에서도 제거한다. */
    @Transactional
    public StoredFileInfo storePhoto(UUID companyId, String contentType, byte[] content) {
        StoredFile file = new StoredFile(companyId, "photo", contentType, content.length);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == STATUS_ROLLED_BACK) {
                    try {
                        storage.delete(file.getStorageKey());
                    } catch (RuntimeException exception) {
                        LOG.error("Failed to remove rolled back photo {}", file.getId(), exception);
                    }
                }
            }
        });
        storage.save(file.getStorageKey(), content);
        return toInfo(files.save(file));
    }

    /** PDF만 받는다. 확장자, 형식 표시와 관계없이 파일 내용이 PDF가 아니면 400을 돌려준다. */
    @Transactional
    public StoredFileInfo storePdf(UUID companyId, String originalName, byte[] content) {
        if (content.length < 5 || !new String(content, 0, 5, StandardCharsets.US_ASCII)
                .equals("%PDF-")) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_FILE", "Only PDF files are allowed.");
        }
        String name = originalName == null || originalName.isBlank() ? "document.pdf" : originalName;
        return store(companyId, name, "application/pdf", content);
    }

    @Transactional(readOnly = true)
    public StoredFileInfo info(UUID companyId, UUID fileId) {
        return toInfo(find(companyId, fileId));
    }

    @Transactional(readOnly = true)
    public FileContent read(UUID companyId, UUID fileId) {
        StoredFile file = find(companyId, fileId);
        return new FileContent(toInfo(file), storage.load(file.getStorageKey()));
    }

    private StoredFile find(UUID companyId, UUID fileId) {
        return files.findByIdAndCompanyId(fileId, companyId)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "FILE_NOT_FOUND", "File not found."));
    }

    private static StoredFileInfo toInfo(StoredFile file) {
        return new StoredFileInfo(file.getId(), file.getOriginalName(), file.getContentType(), file.getSizeBytes());
    }
}
