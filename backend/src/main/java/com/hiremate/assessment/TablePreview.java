package com.hiremate.assessment;

import java.util.List;

/** 결과표 미리보기. 화면에서 열을 결과 항목에 연결한다. */
public record TablePreview(String fileName, List<String> columns, List<List<String>> rows) {
}
