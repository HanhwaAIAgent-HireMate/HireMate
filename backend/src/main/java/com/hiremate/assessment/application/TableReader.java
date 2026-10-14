package com.hiremate.assessment.application;

import com.hiremate.global.ApiException;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import org.springframework.http.HttpStatus;

/** 결과표(CSV · XLSX)의 첫 시트를 행 목록으로 읽는다. 첫 행은 열 이름이다. */
public final class TableReader {

    private static final int MAX_ROWS = 2000;
    private static final Pattern SHARED = Pattern.compile("<si>(.*?)</si>", Pattern.DOTALL);
    private static final Pattern TEXT = Pattern.compile("<t[^>]*>(.*?)</t>", Pattern.DOTALL);
    private static final Pattern ROW = Pattern.compile("<row[^>]*>(.*?)</row>", Pattern.DOTALL);
    private static final Pattern CELL = Pattern.compile("<c ([^>]*?)(?:/>|>(.*?)</c>)", Pattern.DOTALL);
    private static final Pattern REF = Pattern.compile("r=\"([A-Z]+)\\d+\"");
    private static final Pattern VALUE = Pattern.compile("<v>(.*?)</v>", Pattern.DOTALL);

    private TableReader() {
    }

    public static List<List<String>> read(String fileName, byte[] content) {
        String name = fileName == null ? "" : fileName.toLowerCase(Locale.ROOT);
        List<List<String>> rows = name.endsWith(".xlsx") ? xlsx(content) : csv(content);
        if (rows.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "EMPTY_TABLE", "The table has no rows.");
        }
        return rows.size() > MAX_ROWS ? rows.subList(0, MAX_ROWS) : rows;
    }

    static List<List<String>> csv(byte[] content) {
        String text = new String(content, StandardCharsets.UTF_8).replace("﻿", "");
        List<List<String>> rows = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (quoted) {
                if (ch == '"' && i + 1 < text.length() && text.charAt(i + 1) == '"') {
                    cell.append('"');
                    i++;
                } else if (ch == '"') {
                    quoted = false;
                } else {
                    cell.append(ch);
                }
            } else if (ch == '"') {
                quoted = true;
            } else if (ch == ',') {
                row.add(cell.toString().trim());
                cell.setLength(0);
            } else if (ch == '\n' || ch == '\r') {
                if (ch == '\r' && i + 1 < text.length() && text.charAt(i + 1) == '\n') {
                    i++;
                }
                row.add(cell.toString().trim());
                cell.setLength(0);
                addRow(rows, row);
                row = new ArrayList<>();
            } else {
                cell.append(ch);
            }
        }
        row.add(cell.toString().trim());
        addRow(rows, row);
        return rows;
    }

    /** 공유 문자열과 첫 시트만 읽는 최소한의 XLSX 읽기. 수식은 저장된 값을 쓴다. */
    static List<List<String>> xlsx(byte[] content) {
        Map<String, String> parts = new HashMap<>();
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(content))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                String name = entry.getName();
                if (name.equals("xl/sharedStrings.xml") || name.equals("xl/worksheets/sheet1.xml")) {
                    parts.put(name, new String(zip.readAllBytes(), StandardCharsets.UTF_8));
                }
            }
        } catch (IOException exception) {
            throw invalid();
        }
        String sheet = parts.get("xl/worksheets/sheet1.xml");
        if (sheet == null) {
            throw invalid();
        }
        List<String> shared = new ArrayList<>();
        Matcher si = SHARED.matcher(parts.getOrDefault("xl/sharedStrings.xml", ""));
        while (si.find()) {
            StringBuilder text = new StringBuilder();
            Matcher t = TEXT.matcher(si.group(1));
            while (t.find()) {
                text.append(t.group(1));
            }
            shared.add(unescape(text.toString()));
        }
        List<List<String>> rows = new ArrayList<>();
        Matcher row = ROW.matcher(sheet);
        while (row.find()) {
            TreeMap<Integer, String> cells = new TreeMap<>();
            Matcher cell = CELL.matcher(row.group(1));
            while (cell.find()) {
                Matcher ref = REF.matcher(cell.group(1));
                if (!ref.find()) {
                    continue;
                }
                String body = cell.group(2) == null ? "" : cell.group(2);
                Matcher value = VALUE.matcher(body);
                String raw = value.find() ? value.group(1) : "";
                String text;
                if (cell.group(1).contains("t=\"s\"") && !raw.isEmpty()) {
                    text = shared.get(Integer.parseInt(raw.trim()));
                } else if (cell.group(1).contains("t=\"inlineStr\"")) {
                    Matcher inline = TEXT.matcher(body);
                    text = inline.find() ? unescape(inline.group(1)) : "";
                } else {
                    text = unescape(raw);
                }
                cells.put(column(ref.group(1)), text.trim());
            }
            List<String> values = new ArrayList<>();
            if (!cells.isEmpty()) {
                for (int i = 0; i <= cells.lastKey(); i++) {
                    values.add(cells.getOrDefault(i, ""));
                }
            }
            addRow(rows, values);
        }
        return rows;
    }

    private static void addRow(List<List<String>> rows, List<String> row) {
        if (row.stream().anyMatch(value -> !value.isBlank())) {
            rows.add(row);
        }
    }

    private static int column(String letters) {
        int index = 0;
        for (char letter : letters.toCharArray()) {
            index = index * 26 + (letter - 'A' + 1);
        }
        return index - 1;
    }

    private static String unescape(String text) {
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&apos;", "'")
                .replace("&amp;", "&");
    }

    private static ApiException invalid() {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TABLE", "Upload a CSV or XLSX file.");
    }
}
