package com.hiremate.screening;

/** AI Chat 요청에 따른 선택 지원자 변경: "~ 찾아줘"는 교체, "~도 추가해줘"는 추가, "그중 ~"은 좁히기 (FR-15). */
public enum SelectionMode {
    REPLACE,
    ADD,
    NARROW
}
