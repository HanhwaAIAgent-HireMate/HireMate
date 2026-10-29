package com.hiremate.assessment.application;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class TableReaderTests {

    @Test
    @DisplayName("CSV는 따옴표 안의 쉼표와 BOM을 처리한다")
    void readsCsv() {
        byte[] csv = "﻿이메일,총점,비고\na@example.com,88,\"좋음, 협업\"\n".getBytes(StandardCharsets.UTF_8);

        List<List<String>> rows = TableReader.read("result.csv", csv);

        assertThat(rows).containsExactly(List.of("이메일", "총점", "비고"), List.of("a@example.com", "88", "좋음, 협업"));
    }

    @Test
    @DisplayName("XLSX 첫 시트의 공유 문자열과 숫자를 읽는다")
    void readsXlsx() throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(out)) {
            zip.putNextEntry(new ZipEntry("xl/sharedStrings.xml"));
            zip.write("<sst><si><t>이메일</t></si><si><t>총점</t></si><si><t>a@example.com</t></si></sst>"
                    .getBytes(StandardCharsets.UTF_8));
            zip.putNextEntry(new ZipEntry("xl/worksheets/sheet1.xml"));
            zip.write(("<worksheet><sheetData><row r=\"1\"><c r=\"A1\" t=\"s\"><v>0</v></c>"
                    + "<c r=\"B1\" t=\"s\"><v>1</v></c></row>"
                    + "<row r=\"2\"><c r=\"A2\" t=\"s\"><v>2</v></c><c r=\"B2\"><v>91</v></c></row>"
                    + "</sheetData></worksheet>").getBytes(StandardCharsets.UTF_8));
        }

        List<List<String>> rows = TableReader.read("result.xlsx", out.toByteArray());

        assertThat(rows).containsExactly(List.of("이메일", "총점"), List.of("a@example.com", "91"));
    }

    @Test
    @DisplayName("XLSX에 한글이 숫자 표기(&#51060; · &#xC774;)로 저장돼 있어도 한글 그대로 읽는다")
    void readsXlsxWithCharacterReferences() throws Exception {
        // 한글을 그대로 저장한 파일과 숫자 표기로 저장한 파일은 같은 표다
        String korean = "<row r=\"1\"><c r=\"A1\" t=\"inlineStr\"><is><t>이메일</t></is></c>"
                + "<c r=\"B1\" t=\"inlineStr\"><is><t>A&amp;B</t></is></c></row>";
        String references = "<row r=\"1\"><c r=\"A1\" t=\"inlineStr\"><is><t>&#51060;&#xBA54;&#51068;</t></is></c>"
                + "<c r=\"B1\" t=\"inlineStr\"><is><t>A&amp;B</t></is></c></row>";

        assertThat(TableReader.read("plain.xlsx", sheet(korean))).containsExactly(List.of("이메일", "A&B"));
        assertThat(TableReader.read("references.xlsx", sheet(references))).containsExactly(List.of("이메일", "A&B"));
    }

    @Test
    @DisplayName("공유 문자열의 숫자 표기도 풀고, 글자 그대로의 &amp;#51060;은 바꾸지 않는다")
    void readsSharedStringReferences() throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(out)) {
            zip.putNextEntry(new ZipEntry("xl/sharedStrings.xml"));
            zip.write("<sst><si><t>&#52509;&#51216;</t></si><si><t>&amp;#51060;</t></si></sst>"
                    .getBytes(StandardCharsets.UTF_8));
            zip.putNextEntry(new ZipEntry("xl/worksheets/sheet1.xml"));
            zip.write(("<worksheet><sheetData><row r=\"1\"><c r=\"A1\" t=\"s\"><v>0</v></c>"
                    + "<c r=\"B1\" t=\"s\"><v>1</v></c></row></sheetData></worksheet>")
                    .getBytes(StandardCharsets.UTF_8));
        }

        assertThat(TableReader.read("result.xlsx", out.toByteArray())).containsExactly(List.of("총점", "&#51060;"));
    }

    private static byte[] sheet(String rows) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(out)) {
            zip.putNextEntry(new ZipEntry("xl/worksheets/sheet1.xml"));
            zip.write(("<worksheet><sheetData>" + rows + "</sheetData></worksheet>").getBytes(StandardCharsets.UTF_8));
        }
        return out.toByteArray();
    }
}
