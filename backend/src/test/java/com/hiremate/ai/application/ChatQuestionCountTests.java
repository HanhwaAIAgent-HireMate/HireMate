package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.global.ApiException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class ChatQuestionCountTests {

    @ParameterizedTest
    @CsvSource({"질문 만들어줘,2", "1개 만들어줘,1", "질문 5문항 추가해줘,5", "지원자 2명에게 질문 4개,4", "100개,100"})
    @DisplayName("질문 개수는 생략하면 2개이고 지정하면 이전 3개 상한 없이 해당 수를 전달한다")
    void readsRequestedCount(String message, int expected) {
        assertThat(ChatService.requestedQuestionCount(message)).isEqualTo(expected);
    }

    @ParameterizedTest
    @ValueSource(strings = {"질문 0개", "질문 99999999999999999999999개"})
    @DisplayName("유효하지 않은 질문 개수는 자동 실행 전에 거부한다")
    void rejectsInvalidCount(String message) {
        assertThatThrownBy(() -> ChatService.requestedQuestionCount(message)).isInstanceOf(ApiException.class);
    }
}
