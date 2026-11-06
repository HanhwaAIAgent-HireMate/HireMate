package com.hiremate.apply;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.hiremate.posting.DocumentType;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/** 코드가 식별자와 버전을 부여한 정제 문서. */
public record NormalizedDocument(int schemaVersion, UUID documentId, int revision,
                                 DocumentType documentType, List<Block> blocks) {
    public static final String VISUAL_NOTICE = "관련 시각 자료가 있을 수 있습니다. 원본 PDF를 확인해 주세요.";
    public static final String CODE_NOTICE = "코드 예시가 포함되어 있습니다. 원본 PDF를 확인해 주세요.";

    public NormalizedDocument {
        validateMetadata(documentId, revision, documentType);
        if (schemaVersion != 1) {
            throw new IllegalArgumentException("Unsupported schema version");
        }
        blocks = List.copyOf(blocks);
        Set<String> ids = new HashSet<>();
        for (Block block : flatten(blocks)) {
            if (!ids.add(block.id())) {
                throw new IllegalArgumentException("Duplicate block ID");
            }
        }
    }

    static void validateMetadata(UUID documentId, int revision, DocumentType type) {
        Objects.requireNonNull(documentId);
        Objects.requireNonNull(type);
        if (revision < 1 || type == DocumentType.CERTIFICATE) {
            throw new IllegalArgumentException("Invalid document revision or type");
        }
    }

    private static List<Block> flatten(List<Block> blocks) {
        List<Block> result = new ArrayList<>();
        for (Block block : blocks) {
            result.add(block);
            if (block instanceof Section section) {
                result.addAll(flatten(section.blocks()));
            }
        }
        return result;
    }

    public void validateSources(List<DocumentSource> sources) {
        Set<String> ids = new HashSet<>();
        for (DocumentSource source : sources) {
            if (!ids.add(source.id())) {
                throw new IllegalArgumentException("Duplicate source ID");
            }
        }
        for (Block block : flatten(blocks)) {
            if (!ids.containsAll(block.sourceIds())) {
                throw new IllegalArgumentException("Unknown source ID");
            }
        }
    }

    private static void validateBlock(String id, List<String> sourceIds) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(sourceIds);
        if (id.isBlank() || sourceIds.stream().anyMatch(value -> value == null || value.isBlank())) {
            throw new IllegalArgumentException("Invalid block or source ID");
        }
    }

    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
    @JsonSubTypes({
        @JsonSubTypes.Type(value = Section.class, name = "section"),
        @JsonSubTypes.Type(value = Paragraph.class, name = "paragraph"),
        @JsonSubTypes.Type(value = Listing.class, name = "list"),
        @JsonSubTypes.Type(value = Table.class, name = "table"),
        @JsonSubTypes.Type(value = Reference.class, name = "reference")
    })
    public sealed interface Block permits Section, Paragraph, Listing, Table, Reference {
        String id();

        List<String> sourceIds();
    }

    public record Section(String id, List<String> sourceIds, String title, List<Block> blocks) implements Block {
        public Section {
            validateBlock(id, sourceIds);
            sourceIds = List.copyOf(sourceIds);
            blocks = List.copyOf(blocks);
            if (title == null && !sourceIds.isEmpty()) {
                throw new IllegalArgumentException("Untitled sections cannot have title sources");
            }
        }
    }

    public record Paragraph(String id, List<String> sourceIds, String role, String text) implements Block {
        public Paragraph {
            validateBlock(id, sourceIds);
            sourceIds = List.copyOf(sourceIds);
            Objects.requireNonNull(text);
            if (role == null || !Set.of("body", "caption", "page_header", "page_footer",
                    "form_instruction", "unassigned").contains(role)) {
                throw new IllegalArgumentException("Unknown paragraph role");
            }
        }
    }

    public record ListItem(String marker, String text, List<ListItem> children) {
        public ListItem {
            Objects.requireNonNull(text);
            children = List.copyOf(children);
        }
    }

    public record Listing(String id, List<String> sourceIds, List<ListItem> items) implements Block {
        public Listing {
            validateBlock(id, sourceIds);
            sourceIds = List.copyOf(sourceIds);
            items = List.copyOf(items);
        }
    }

    public record Table(String id, List<String> sourceIds, String caption,
                        List<String> headers, List<List<String>> rows) implements Block {
        public Table {
            validateBlock(id, sourceIds);
            sourceIds = List.copyOf(sourceIds);
            headers = java.util.Collections.unmodifiableList(new ArrayList<>(headers));
            rows = rows.stream().map(row -> java.util.Collections.unmodifiableList(new ArrayList<>(row))).toList();
        }
    }

    public record Reference(String id, List<String> sourceIds, String kind,
                            String text, String notice) implements Block {
        public Reference {
            validateBlock(id, sourceIds);
            sourceIds = List.copyOf(sourceIds);
            String expected = switch (Objects.requireNonNull(kind)) {
                case "possible_visual" -> VISUAL_NOTICE;
                case "code_example" -> CODE_NOTICE;
                default -> throw new IllegalArgumentException("Unknown reference kind");
            };
            if (!expected.equals(notice)) {
                throw new IllegalArgumentException("Reference notice must be assigned by code");
            }
        }
    }
}
