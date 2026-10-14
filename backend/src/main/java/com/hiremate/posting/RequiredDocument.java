package com.hiremate.posting;

public record RequiredDocument(DocumentType type, String label, String format, boolean required) {
}
