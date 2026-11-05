package com.hiremate.mail;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * 메일 한 통의 내용. 같은 내용으로 텍스트 메일과 HTML 메일을 만든다.
 * 텍스트 메일은 본문 블록, 맺음말, 바닥글을 빈 줄로 이어 붙인 글이다. 비어 있는 부분은 넣지 않는다.
 *
 * @param sender 머리글에 쓰는 보내는 회사 이름
 * @param caption 제목 위에 작게 쓰는 공고명
 * @param blocks 본문. 문단 글이나 안내 상자
 * @param closing 맺음말. 없으면 빈 문자열
 * @param footer 맨 아래 바닥글 (필수 문구)
 */
public record MailContent(String sender, String caption, List<Block> blocks, String closing, String footer) {

    public String text() {
        return Stream.concat(blocks.stream().map(Block::text), Stream.of(closing, footer))
                .filter(part -> !part.isBlank())
                .collect(Collectors.joining("\n\n"));
    }

    /** {지원자명} 같은 변수를 값으로 바꾼 내용. 지원자마다 채워 보낸다. */
    public MailContent fill(Map<String, String> values) {
        return new MailContent(replace(sender, values), replace(caption, values),
                blocks.stream().map(block -> block.fill(values)).toList(), replace(closing, values),
                replace(footer, values));
    }

    static String replace(String text, Map<String, String> values) {
        String filled = text;
        for (Map.Entry<String, String> value : values.entrySet()) {
            filled = filled.replace(value.getKey(), value.getValue());
        }
        return filled;
    }

    public sealed interface Block permits Text, Guide {

        String text();

        Block fill(Map<String, String> values);
    }

    /** 문단 글. 빈 줄로 문단을 나눈다. */
    public record Text(String text) implements Block {

        @Override
        public Text fill(Map<String, String> values) {
            return new Text(replace(text, values));
        }
    }

    /**
     * 전형 안내 · 입사 안내처럼 칸이 나뉜 안내 상자. 텍스트 메일에서는 ■ 제목 아래 "- 칸: 값" 줄과 ※ 줄이다.
     *
     * @param lead 상자 앞에 쓰는 한 문장
     * @param items 값이 있는 칸만
     * @param notes 기타 안내. 한 줄에 하나
     */
    public record Guide(String lead, String title, List<Item> items, List<String> notes) implements Block {

        @Override
        public String text() {
            List<String> lines = new ArrayList<>(List.of(lead, "", "■ " + title));
            items.forEach(item -> lines.add("- " + item.label() + ": " + item.value()));
            if (!notes.isEmpty()) {
                lines.add("");
                notes.forEach(note -> lines.add("※ " + note));
            }
            return String.join("\n", lines);
        }

        @Override
        public Guide fill(Map<String, String> values) {
            return new Guide(replace(lead, values), replace(title, values),
                    items.stream().map(item -> new Item(item.label(), replace(item.value(), values), item.hint()))
                            .toList(),
                    notes.stream().map(note -> replace(note, values)).toList());
        }
    }

    /**
     * 안내 상자의 칸 하나.
     *
     * @param hint 미리보기에서만 값 아래에 흐리게 쓰는 메모. 텍스트 메일에는 넣지 않는다. 없으면 빈 문자열
     */
    public record Item(String label, String value, String hint) {

        public Item(String label, String value) {
            this(label, value, "");
        }
    }
}
