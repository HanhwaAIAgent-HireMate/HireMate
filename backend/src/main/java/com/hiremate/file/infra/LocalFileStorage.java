package com.hiremate.file.infra;

import com.hiremate.file.application.FileStorage;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 로컬 디스크 저장소. 운영의 비공개 S3 저장소가 생기기 전까지 쓴다. */
@Component
@ConditionalOnProperty(prefix = "hiremate.files", name = "storage", havingValue = "local", matchIfMissing = true)
class LocalFileStorage implements FileStorage {

    private final Path root;

    LocalFileStorage(@Value("${hiremate.files.local-dir}") String root) {
        this.root = Path.of(root).toAbsolutePath().normalize();
    }

    @Override
    public void save(String key, byte[] content) {
        Path target = resolve(key);
        try {
            Files.createDirectories(target.getParent());
            Files.write(target, content);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    @Override
    public byte[] load(String key) {
        try {
            return Files.readAllBytes(resolve(key));
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    @Override
    public void delete(String key) {
        try {
            Files.deleteIfExists(resolve(key));
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    private Path resolve(String key) {
        Path target = root.resolve(key).normalize();
        if (!target.startsWith(root)) {
            throw new IllegalArgumentException("Invalid storage key.");
        }
        return target;
    }
}
