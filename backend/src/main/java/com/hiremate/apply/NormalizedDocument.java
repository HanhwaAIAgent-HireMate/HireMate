package com.hiremate.apply;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.hiremate.posting.BlindMask;
import com.hiremate.posting.DocumentType;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.UnaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/** 제출 PDF를 정책에 따라 정리한 페이지 기반 문서. */
public record NormalizedDocument(String schemaVersion, Metadata document, List<Block> blocks) {
    public NormalizedDocument {
        if (!"1.0".equals(schemaVersion)) {
            throw new IllegalArgumentException("Unsupported document schema");
        }
        Objects.requireNonNull(document);
        blocks = List.copyOf(blocks);
        Set<String> ids = new HashSet<>();
        for (Block block : blocks) {
            validate(block, document.pageCount(), ids);
        }
        checkText(document.title());
    }

    static void validateMetadata(UUID documentId, int revision, DocumentType type) {
        Objects.requireNonNull(documentId);
        Objects.requireNonNull(type);
        if (revision < 1 || type == DocumentType.CERTIFICATE) {
            throw new IllegalArgumentException("Invalid document revision or type");
        }
    }

    /** 저장된 JSON을 바꾸지 않고 기존 가림 규칙을 검색용 복사본에 적용한다. */
    public NormalizedDocument forSearch(String name, boolean blind) {
        UnaryOperator<String> mask = value -> value == null ? null
                : BlindMask.maskApplicant(blind ? BlindMask.mask(value) : value, name);
        var metadata = new Metadata(document.id(), document.type(), mask.apply(document.title()), document.pageCount());
        return new NormalizedDocument(schemaVersion, metadata,
                blocks.stream().map(block -> maskBlock(block, mask)).toList());
    }

    private static Block maskBlock(Block block, UnaryOperator<String> mask) {
        return switch (block) {
            case Section section -> new Section(section.id(), section.pages(), mask.apply(section.title()),
                    section.blocks().stream().map(child -> maskBlock(child, mask)).toList());
            case Paragraph paragraph -> new Paragraph(paragraph.id(), paragraph.pages(), mask.apply(paragraph.text()));
            case Listing listing -> new Listing(listing.id(), listing.pages(),
                    listing.items().stream().map(item -> maskItem(item, mask)).toList());
            case Table table -> new Table(table.id(), table.pages(), mask.apply(table.title()),
                    table.headers().stream().map(mask).toList(),
                    table.rows().stream().map(row -> row.stream().map(mask).toList()).toList(), table.reconstruction());
            case VisualNotice notice -> new VisualNotice(notice.id(), notice.pages(), notice.visualType(),
                    notice.detection(), mask.apply(notice.message()));
        };
    }

    private static ListItem maskItem(ListItem item, UnaryOperator<String> mask) {
        return new ListItem(item.id(), mask.apply(item.text()), item.pages(),
                item.items().stream().map(child -> maskItem(child, mask)).toList());
    }

    /**
     * 읽는 순서대로 펼친 글. 정제를 마친 서류는 PDF에서 뽑은 글 대신 이 글을 AI에 보낸다 (ApplicantDocument.text).
     * 순서는 화면이 근거 밑줄 자리를 찾는 칸 순서(문서 제목, 소제목, 문단, 목록 항목, 표 제목 · 머리글 · 칸)와 같아, 이 글에서
     * 뽑은 근거 문장을 화면도 찾는다. 시각 자료 안내(visual_notice)는 지원자가 쓴 글이 아니라 넣지 않는다.
     */
    public String readingText() {
        return Stream.concat(Stream.of(document.title()), blocks.stream().flatMap(NormalizedDocument::lines))
                .filter(line -> line != null && !line.isBlank())
                .collect(Collectors.joining("\n"));
    }

    private static Stream<String> lines(Block block) {
        return switch (block) {
            case Section section -> Stream.concat(Stream.of(section.title()),
                    section.blocks().stream().flatMap(NormalizedDocument::lines));
            case Paragraph paragraph -> Stream.of(paragraph.text());
            case Listing listing -> items(listing.items(), 0);
            case Table table -> Stream.concat(Stream.of(table.title(), String.join(" | ", table.headers())),
                    table.rows().stream().map(row -> String.join(" | ", row)));
            case VisualNotice notice -> Stream.empty();
        };
    }

    /** 목록 항목은 '- '를 붙이고, 아래 항목은 두 칸씩 들여 쓴다. */
    private static Stream<String> items(List<ListItem> items, int depth) {
        return items.stream().flatMap(item -> Stream.concat(Stream.of("  ".repeat(depth) + "- " + item.text()),
                items(item.items(), depth + 1)));
    }

    private static void checkText(String text) {
        if (text != null && text.indexOf((char) 183) >= 0) {
            throw new IllegalArgumentException("Unprocessed character in normalized document");
        }
    }

    private static void validateItem(String id, List<Integer> pages, int pageCount, Set<String> ids) {
        if (id == null || id.isBlank() || !ids.add(id) || pages == null
                || pages.stream().anyMatch(page -> page == null || page < 1 || page > pageCount)) {
            throw new IllegalArgumentException("Invalid block ID or page");
        }
    }

    private static void validateListItem(ListItem item, int pageCount, Set<String> ids) {
        validateItem(item.id(), item.pages(), pageCount, ids);
        checkText(item.text());
        item.items().forEach(child -> validateListItem(child, pageCount, ids));
    }

    private static void validate(Block block, int pageCount, Set<String> ids) {
        validateItem(block.id(), block.pages(), pageCount, ids);
        switch (block) {
            case Section section -> {
                checkText(section.title());
                section.blocks().forEach(child -> validate(child, pageCount, ids));
            }
            case Paragraph paragraph -> checkText(paragraph.text());
            case Listing listing -> listing.items().forEach(item -> validateListItem(item, pageCount, ids));
            case Table table -> {
                checkText(table.title());
                table.headers().forEach(NormalizedDocument::checkText);
                table.rows().forEach(row -> row.forEach(NormalizedDocument::checkText));
            }
            case VisualNotice notice -> checkText(notice.message());
        }
    }

    public record Metadata(UUID id, String type, String title, int pageCount) {
        public Metadata {
            Objects.requireNonNull(id);
            if (type == null || !Set.of("resume", "cover_letter", "portfolio").contains(type) || pageCount < 1) {
                throw new IllegalArgumentException("Invalid document metadata");
            }
        }
    }

    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
    @JsonSubTypes({
            @JsonSubTypes.Type(value = Section.class, name = "section"),
            @JsonSubTypes.Type(value = Paragraph.class, name = "paragraph"),
            @JsonSubTypes.Type(value = Listing.class, name = "list"),
            @JsonSubTypes.Type(value = Table.class, name = "table"),
            @JsonSubTypes.Type(value = VisualNotice.class, name = "visual_notice")
    })
    public sealed interface Block permits Section, Paragraph, Listing, Table, VisualNotice {
        String id();

        List<Integer> pages();
    }

    public record Section(String id, List<Integer> pages, String title, List<Block> blocks) implements Block {
        public Section {
            pages = List.copyOf(pages);
            blocks = List.copyOf(blocks);
        }
    }

    public record Paragraph(String id, List<Integer> pages, String text) implements Block {
        public Paragraph {
            pages = List.copyOf(pages);
            Objects.requireNonNull(text);
        }
    }

    public record ListItem(String id, String text, List<Integer> pages, List<ListItem> items) {
        public ListItem {
            Objects.requireNonNull(text);
            pages = List.copyOf(pages);
            items = List.copyOf(items);
        }
    }

    public record Listing(String id, List<Integer> pages, List<ListItem> items) implements Block {
        public Listing {
            pages = List.copyOf(pages);
            items = List.copyOf(items);
        }
    }

    public record Table(String id, List<Integer> pages, String title, List<String> headers,
                        List<List<String>> rows, String reconstruction) implements Block {
        public Table {
            pages = List.copyOf(pages);
            headers = List.copyOf(headers);
            rows = rows.stream().map(List::copyOf).toList();
            if (!"inferred".equals(reconstruction)) {
                throw new IllegalArgumentException("Invalid table reconstruction");
            }
        }
    }

    public record VisualNotice(String id, List<Integer> pages, String visualType, String detection,
                               String message) implements Block {
        public VisualNotice {
            pages = List.copyOf(pages);
            Objects.requireNonNull(message);
            if (visualType == null || !Set.of("image", "chart", "diagram", "unknown").contains(visualType)
                    || !"suspected".equals(detection)) {
                throw new IllegalArgumentException("Invalid visual notice");
            }
        }
    }
}
