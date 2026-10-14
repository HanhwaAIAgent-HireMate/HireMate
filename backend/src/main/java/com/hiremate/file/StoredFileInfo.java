package com.hiremate.file;

import java.util.UUID;

public record StoredFileInfo(UUID fileId, String originalName, String contentType, long size) {
}
