package com.hiremate.file;

import com.hiremate.file.application.FileStorage;
import com.hiremate.file.domain.StoredFile;
import com.hiremate.file.domain.StoredFileRepository;
import com.hiremate.global.ApiException;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 파일을 기업 단위로 저장하고 읽는다. 다른 기업의 파일은 찾지 못한 것으로 다룬다. */
@Service
public class FileService {

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
