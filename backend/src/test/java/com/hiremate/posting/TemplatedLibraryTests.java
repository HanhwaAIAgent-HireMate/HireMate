package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class TemplatedLibraryTests {
    private final JsonMapper json = new JsonMapper();

    @Test
    void returnsThreeDistinctRelevantThemesAndRejectsUnsupportedPhotos() {
        List<JsonNode> rows = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            rows.add(template(i, "recruitment theme " + i, "shape"));
        }
        rows.add(template(8, "recruitment theme 0", "shape"));
        rows.add(template(9, "recruitment photo", "image"));
        assertThat(TemplatedLibrary.candidates(rows, "recruitment")).hasSize(3)
                .extracting(PosterProposal.FreeTemplate::name).doesNotHaveDuplicates();
        assertThat(TemplatedLibrary.candidates(rows, "unavailable")).isEmpty();
        assertThat(TemplatedLibrary.preview(template(9, "photo", "image"))).isNull();
    }

    @Test
    void excludesSameLayoutEvenWhenIdNameAndColorDiffer() {
        JsonNode first = template(1, "recruitment original", "shape");
        JsonNode clone = json.readTree(first.toString().replace("original", "clone")
                .replace("000000000001", "000000000009").replace("#082858", "#ff8800"));
        assertThat(TemplatedLibrary.candidates(List.of(first, clone), "recruitment")).hasSize(1);
    }

    @Test
    void reconstructsSafePreviewWithoutExecutingExternalHtmlOrUrls() {
        JsonNode row = json.readTree("""
                {"width":1080,"height":2400,"background":"url(https://evil.example)","layers":[
                  {"type":"shape","x":0,"y":0,"width":1080,"height":860,"fill":"#082858"},
                  {"type":"text","x":80,"y":910,"font_size":"32px","color":"#ffffff",
                   "text":"<script>secret</script><img src=x onerror=alert(1)>회사 소개 & 안내"}
                ]}
                """);
        assertThat(TemplatedLibrary.preview(row)).contains("data-body-top=\"860.0\"", "회사 소개 &amp; 안내")
                .doesNotContain("<script", "<img", "onerror", "evil.example");
    }

    private JsonNode template(int number, String name, String type) {
        return json.readTree("""
                {"id":"00000000-0000-0000-0000-%012d","name":"%s","width":600,"height":1200,
                 "layers":[{"type":"%s","x":0,"y":0,"width":600,"height":%d,"fill":"#082858"}]}
                """.formatted(number, name, type, 300 + number * 20));
    }
}
