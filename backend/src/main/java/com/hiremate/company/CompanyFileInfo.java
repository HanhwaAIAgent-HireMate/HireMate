package com.hiremate.company;

import java.time.Instant;
import java.util.UUID;

public record CompanyFileInfo(UUID fileId, CompanyFileCategory category, String name, long size, Instant uploadedAt) {
}
