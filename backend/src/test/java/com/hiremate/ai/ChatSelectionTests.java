package com.hiremate.ai;

import static com.hiremate.TestApi.done;
import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.ai.application.ChatApplied;
import com.hiremate.ai.application.ChatHistoryTurn;
import com.hiremate.ai.application.ChatItem;
import com.hiremate.ai.application.ChatPlan;
import com.hiremate.ai.application.RootAgent;
import com.hiremate.apply.ApplicationAnalysis;
import com.hiremate.apply.ApplicationService;
import com.hiremate.apply.CriterionMark;
import com.hiremate.apply.QualificationStatus;
import com.hiremate.global.ApiException;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.SelectionMode;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.JsonNode;

class ChatSelectionTests extends IntegrationTest {

    @MockitoBean
    private RootAgent root;

    @Autowired
    private ApplicationService applications;

    @Autowired
    private ScreeningService screening;

    @Test
    @DisplayName("이미 선택한 지원자 추가는 변경 없이 알리고 AI 표시를 유지한다")
    void duplicateEditAdditionKeepsExistingSelection() throws Exception {
        Setup setup = documentStage();
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.REPLACE, setup.ids());
        ChatPlan previous = new ChatPlan(ChatPlan.Intent.EDIT, null,
                ChatPlan.EditAction.ADD, setup.ids(), "2명을 선택 지원자에 넣었어요.", List.of(),
                List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isFalse();
        assertThat(answer.path("message").asString()).contains("이미", "2명").doesNotContain("넣었어요");
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .allMatch(row -> row.selected() && row.aiSelected());
        assertHistoryMatches(setup, previous, answer, applied.get());
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    @DisplayName("일부 지원자를 추가할 수 없는 이유는 실제 추가 수를 보정한 뒤에도 보존한다")
    void mixedAdditionKeepsRejectedApplicantReason(boolean alreadySelected) throws Exception {
        Setup setup = documentStage();
        UUID target = setup.ids().getFirst();
        UUID rejected = setup.ids().get(1);
        screening.decide(setup.hr().companyId(), setup.stageId(), setup.hr().memberId(), List.of(rejected),
                Decision.PASS);
        if (alreadySelected) {
            screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), List.of(target));
        }
        String reason = "지원자2 님은 이미 합격 처리한 지원자라 선택 지원자에 넣을 수 없어요.";
        ChatPlan previous = new ChatPlan(ChatPlan.Intent.EDIT, null, ChatPlan.EditAction.ADD, List.of(target),
                "지원자1 님을 선택 지원자에 넣었어요. " + reason,
                List.of(new ChatItem(null, "선택 불가", reason, "CHECK")), List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(answer.path("message").asString()).contains(reason);
        if (alreadySelected) {
            assertThat(answer.path("message").asString()).contains("이미 선택").doesNotContain("넣었어요");
        }
        assertThat(answer.path("items").size()).isEqualTo(1);
        assertThat(answer.path("items").get(0).path("applicationId").isNull()).isTrue();
        assertThat(applied.get().plan().message()).isEqualTo(answer.path("message").asString());
        assertThat(applied.get().plan().targets()).hasSize(alreadySelected ? 0 : 1);
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(target);
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("좁히기 결과는 신규 추가 수 대신 유지한 두 명을 알려 주고 직접 넣은 지원자도 AI 선택으로 표시한다")
    void narrowingReportsRetainedApplicants() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        when(root.plan(any(), any())).thenReturn(find(setup, SelectionMode.NARROW));

        JsonNode answer = ask(setup);

        assertThat(answer.path("message").asString()).contains("2명 중", "2명").doesNotContain("0명");
        assertThat(answer.path("items").size()).isEqualTo(2);
        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .hasSize(2).allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("좁히기 대상을 모두 실행할 수 없으면 기존 선택을 보존하고 성공 항목을 내보내지 않는다")
    void rejectedNarrowingKeepsSelectionAndOmitsSuccessItems() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids().subList(0, 1));
        UUID unselected = setup.ids().get(1);
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.NARROW,
                null, List.of(unselected), "2명 중 **{count}명**으로 좁혔어요.",
                List.of(new ChatItem(unselected, "지원자2", "Java Spring", "OK")),
                List.of("이력서"), List.of(), List.of()));

        JsonNode answer = ask(setup);

        assertThat(answer.path("intent").asString()).isEqualTo("CLARIFY");
        assertThat(answer.path("selectionChanged").asBoolean()).isFalse();
        assertThat(answer.path("items").isEmpty()).isTrue();
        assertThat(answer.path("message").asString()).doesNotContain("좁혔어요");
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(setup.ids().getFirst());
    }

    @Test
    @DisplayName("탐색 이후 결정된 지원자는 반영 수와 최종 항목에서 제외한다")
    void searchItemsFollowAppliedApplicants() throws Exception {
        Setup setup = documentStage();
        ChatPlan previous = find(setup, SelectionMode.REPLACE);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);
        when(root.plan(any(), any())).thenAnswer(call -> {
            screening.decide(setup.hr().companyId(), setup.stageId(), setup.hr().memberId(),
                    setup.ids().subList(1, 2), Decision.FAIL);
            return previous;
        });

        JsonNode answer = ask(setup);

        assertThat(answer.path("message").asString()).contains("1명");
        assertThat(answer.path("items").size()).isEqualTo(1);
        assertThat(answer.path("items").get(0).path("applicationId").asString())
                .isEqualTo(setup.ids().getFirst().toString());
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(setup.ids().getFirst());
        assertHistoryMatches(setup, previous, answer, applied.get());
    }

    @Test
    @DisplayName("찾기 추가의 중복 결과는 새로 추가했다고 알리지 않고 이미 있던 지원자를 AI 선택으로 표시한다")
    void duplicateFindAdditionMarksExistingSelection() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        when(root.plan(any(), any())).thenReturn(find(setup, SelectionMode.ADD));

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(answer.path("message").asString()).contains("이미", "2명").doesNotContain("더했어요");
        assertThat(answer.path("items").isEmpty()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .hasSize(2).allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("찾기 추가는 기존 한 명을 보존하고 새로 넣은 한 명만 최종 항목과 추가 수로 알린다")
    void mixedFindAdditionReportsOnlyNewApplicants() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids().subList(0, 1));
        when(root.plan(any(), any())).thenReturn(find(setup, SelectionMode.ADD));

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(answer.path("message").asString()).contains("검색 결과 2명", "**1명**을 새로 추가", "1명은 이미");
        assertThat(answer.path("items").size()).isEqualTo(1);
        assertThat(answer.path("items").get(0).path("applicationId").asString())
                .isEqualTo(setup.ids().get(1).toString());
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .hasSize(2).allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("실제 반영한 탐색 결과를 기록할 때 검색 순서를 유지한다")
    void appliedSearchKeepsResultOrder() throws Exception {
        Setup setup = documentStage();
        ChatPlan previous = find(setup, SelectionMode.REPLACE);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);
        when(root.plan(any(), any())).thenReturn(previous);
        ask(setup);
        List<UUID> reversed = applied.get().plan().targets().reversed();
        ChatPlan reordered = new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null, reversed,
                "검색한 **{count}명**을 선택했어요.", reversed.stream()
                        .map(id -> new ChatItem(id, "지원자", "Java Spring", "OK")).toList(),
                List.of("이력서"), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(reordered);

        JsonNode answer = ask(setup);

        assertThat(applied.get().plan().targets()).containsExactlyElementsOf(reversed);
        assertThat(answer.path("items").get(0).path("applicationId").asString())
                .isEqualTo(reversed.getFirst().toString());
    }

    @Test
    @DisplayName("실제 편집한 지원자를 기록할 때 요청한 대상 순서를 유지한다")
    void appliedEditKeepsTargetOrder() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        ChatPlan previous = new ChatPlan(ChatPlan.Intent.EDIT, null, ChatPlan.EditAction.REMOVE, setup.ids(),
                "선택 지원자에서 {count}명을 뺐어요.", List.of(), List.of(), List.of(), List.of());
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);
        when(root.plan(any(), any())).thenReturn(previous);
        ask(setup);
        List<UUID> reversed = applied.get().plan().targets().reversed();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        ChatPlan reordered = new ChatPlan(ChatPlan.Intent.EDIT, null, ChatPlan.EditAction.REMOVE, reversed,
                "선택 지원자에서 {count}명을 뺐어요.", List.of(), List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(reordered);

        ask(setup);

        assertThat(applied.get().plan().targets()).containsExactlyElementsOf(reversed);
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items()).isEmpty();
    }

    @Test
    @DisplayName("검색 결과가 없으면 조건 불일치를 알리고 기존 선택을 유지한다")
    void emptySearchKeepsNoResultsMessageAndSelection() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        String message = "조건에 맞는 지원자를 찾지 못했어요. 선택 지원자는 그대로예요.";
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null,
                List.of(), message, List.of(), List.of(), List.of(), List.of()));

        JsonNode answer = ask(setup);

        assertThat(answer.path("message").asString()).isEqualTo(message);
        assertThat(answer.path("selectionChanged").asBoolean()).isFalse();
        assertThat(answer.path("items").isEmpty()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items()).hasSize(2);
    }

    @Test
    @DisplayName("이미 결정해 선택에서 빠진 지원자를 빼도 다른 선택과 결정 복구 표시는 유지한다")
    void removingDecidedApplicantPreservesSelectionAndDecisionRestoration() throws Exception {
        Setup setup = documentStage();
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.REPLACE, setup.ids());
        UUID decided = setup.ids().getFirst();
        screening.decide(setup.hr().companyId(), setup.stageId(), setup.hr().memberId(), List.of(decided),
                Decision.PASS);
        ChatPlan previous = new ChatPlan(ChatPlan.Intent.EDIT, null, ChatPlan.EditAction.REMOVE, List.of(decided),
                "지원자1 님을 선택 지원자에서 뺐어요.", List.of(), List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isFalse();
        assertThat(answer.path("message").asString()).contains("현재 선택 지원자에 없어요").doesNotContain("뺐어요");
        assertThat(applied.get().plan().targets()).isEmpty();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(setup.ids().get(1));
        screening.revert(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                setup.hr().memberId(), List.of(decided));
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .filteredOn(row -> row.applicationId().equals(decided)).allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("탐색 결과로 선택을 교체해도 결정된 지원자의 결정 복구 표시는 보존한다")
    void replacingSelectionPreservesDecidedApplicant() throws Exception {
        Setup setup = documentStage();
        UUID decided = setup.ids().getFirst();
        UUID target = setup.ids().get(1);
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.REPLACE, List.of(decided));
        screening.decide(setup.hr().companyId(), setup.stageId(), setup.hr().memberId(), List.of(decided),
                Decision.PASS);
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.REPLACE, null,
                List.of(target), "**{count}명**을 선택했어요.", List.of(), List.of(), List.of(), List.of()));

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(target);
        screening.revert(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                setup.hr().memberId(), List.of(decided));
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .filteredOn(row -> row.applicationId().equals(decided)).allMatch(row -> row.aiSelected());
    }

    @ParameterizedTest
    @EnumSource(value = ChatPlan.EditAction.class, names = {"CLEAR", "RESTORE"})
    @DisplayName("선택을 비우거나 되돌려도 이미 결정된 지원자의 결정 복구 표시는 보존한다")
    void selectionEditPreservesDecidedApplicant(ChatPlan.EditAction action) throws Exception {
        Setup setup = documentStage();
        UUID decided = setup.ids().getFirst();
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.REPLACE, setup.ids());
        screening.clear(setup.hr().companyId(), setup.stageId(), setup.tabId());
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.ADD, List.of(decided));
        screening.decide(setup.hr().companyId(), setup.stageId(), setup.hr().memberId(), List.of(decided),
                Decision.PASS);
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids().subList(1, 2));
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.EDIT, null, action, List.of(),
                "선택 지원자를 편집했어요.", List.of(), List.of(), List.of(), List.of()));

        ask(setup);

        screening.revert(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                setup.hr().memberId(), List.of(decided));
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .filteredOn(row -> row.applicationId().equals(decided)).allMatch(row -> row.aiSelected());
    }

    @Test
    @DisplayName("좁히기는 유지할 대상을 반영하고 되돌리기는 직전 두 명과 수동 선택 표시를 복구한다")
    void narrowingCanRestorePreviousSelection() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        UUID retained = setup.ids().getFirst();
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.FIND, SelectionMode.NARROW,
                null, List.of(retained), "2명 중 **{count}명**으로 좁혔어요.",
                List.of(new ChatItem(retained, "지원자1", "Java Spring", "OK")),
                List.of("이력서"), List.of(), List.of()));

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(answer.path("message").asString()).contains("**1명**으로 좁혔어요");
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .extracting(row -> row.applicationId()).containsExactly(retained);
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .allMatch(row -> row.aiSelected());
        screening.restore(setup.hr().companyId(), setup.stageId(), setup.tabId());
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .hasSize(2).allMatch(row -> !row.aiSelected());
    }

    @Test
    @DisplayName("되돌리기로 대상 수가 같아도 AI 표시가 바뀌면 화면을 갱신한다")
    void restoringSelectionMarksRequiresRefresh() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        screening.clear(setup.hr().companyId(), setup.stageId(), setup.tabId());
        screening.applyAiSelection(setup.hr().companyId(), setup.stageId(), setup.tabId(),
                SelectionMode.ADD, setup.ids());
        when(root.plan(any(), any())).thenReturn(new ChatPlan(ChatPlan.Intent.EDIT, null,
                ChatPlan.EditAction.RESTORE, List.of(), "직전 선택으로 되돌렸어요.", List.of(),
                List.of(), List.of(), List.of()));

        JsonNode answer = ask(setup);

        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items())
                .hasSize(2).allMatch(row -> !row.aiSelected());
    }

    @Test
    @DisplayName("대화 기록 확인 요청이 실패해도 이미 반영한 선택과 성공 응답을 유지한다")
    void confirmationFailureKeepsAppliedSelection() throws Exception {
        Setup setup = documentStage();
        when(root.plan(any(), any())).thenReturn(find(setup, SelectionMode.REPLACE));
        doThrow(new ApiException(HttpStatus.BAD_GATEWAY, "AI_UNAVAILABLE", "unavailable"))
                .when(root).applied(any());

        JsonNode answer = ask(setup);

        assertThat(answer.path("intent").asString()).isEqualTo("FIND");
        assertThat(answer.path("selectionChanged").asBoolean()).isTrue();
        assertThat(screening.selection(setup.hr().companyId(), setup.stageId(), setup.tabId()).items()).hasSize(2);
        verify(root).applied(any());
    }

    @Test
    @DisplayName("끝난 전형도 탭 대화방에 남으므로, 찾기 대신 안내한 응답으로 대화 기록을 보정한다")
    void completedStageConfirmsCorrectedAnswer() throws Exception {
        Setup setup = documentStage();
        ChatPlan previous = find(setup, SelectionMode.REPLACE);
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);
        String path = "/api/stages/" + setup.stageId();
        expect(setup.hr().post(path + "/decisions",
                Map.of("applicationIds", setup.ids(), "decision", "FAIL")), 204);
        expect(setup.hr().post(path + "/confirm", null), 200);
        expect(setup.hr().post(path + "/notices/prepare", null), 200);
        expect(setup.hr().post(path + "/notices/FAIL/send", null), 200);
        expect(setup.hr().post(path + "/finish", null), 200);
        JsonNode answer = ask(setup);

        assertThat(answer.path("intent").asString()).isEqualTo("CLARIFY");
        assertThat(applied.get().threadId()).isEqualTo(setup.threadId());
        assertThat(applied.get().plan().intent()).isEqualTo(ChatPlan.Intent.CLARIFY);
        assertThat(applied.get().plan().message()).isEqualTo(answer.path("message").asString());
    }

    @Test
    @DisplayName("원본과 최종 응답이 같아도 대화 완료를 기록한다")
    void unchangedAnswerConfirmsCompletion() throws Exception {
        Setup setup = documentStage();
        ChatPlan previous = ChatPlan.answer(ChatPlan.Intent.ANSWER, "도움이 필요하면 말씀해 주세요.",
                List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);

        JsonNode answer = ask(setup);

        assertThat(answer.path("message").asString()).isEqualTo(previous.message());
        assertThat(applied.get()).isNotNull();
        assertThat(applied.get().plan()).isEqualTo(previous);
    }

    @Test
    @DisplayName("변경 없이 성공한 빼기도 완료를 기록해 반복 요청의 응답을 보정할 수 있다")
    void successfulRemovalConfirmsBeforeRepeatedCorrection() throws Exception {
        Setup setup = documentStage();
        screening.add(setup.hr().companyId(), setup.stageId(), setup.tabId(), setup.ids());
        ChatPlan previous = new ChatPlan(ChatPlan.Intent.EDIT, null, ChatPlan.EditAction.REMOVE, setup.ids(),
                "지원자1, 지원자2 님을 선택 지원자에서 뺐어요.", List.of(), List.of(), List.of(), List.of());
        when(root.plan(any(), any())).thenReturn(previous);
        AtomicReference<ChatApplied> applied = rememberApplied(setup, previous);

        ask(setup);

        assertThat(applied.get()).isNotNull();
        assertThat(applied.get().plan()).isEqualTo(previous);
        JsonNode repeated = ask(setup);
        assertThat(repeated.path("selectionChanged").asBoolean()).isFalse();
        assertThat(repeated.path("message").asString()).contains("현재 선택 지원자에 없어요");
        assertThat(applied.get().plan().targets()).isEmpty();
        assertThat(applied.get().plan().message()).isEqualTo(repeated.path("message").asString());
    }

    private AtomicReference<ChatApplied> rememberApplied(Setup setup, ChatPlan previous) {
        AtomicReference<ChatApplied> applied = new AtomicReference<>();
        doAnswer(call -> {
            applied.set(call.getArgument(0));
            return null;
        }).when(root).applied(any());
        when(root.history(setup.threadId())).thenAnswer(call -> List.of(new ChatHistoryTurn("선택 요청",
                applied.get() == null ? previous : applied.get().plan(), 2)));
        return applied;
    }

    private static void assertHistoryMatches(Setup setup, ChatPlan previous, JsonNode answer, ChatApplied applied)
            throws Exception {
        assertThat(applied).isNotNull();
        assertThat(applied.threadId()).isEqualTo(setup.threadId());
        assertThat(applied.message()).isEqualTo("선택 요청");
        assertThat(applied.previous()).isEqualTo(previous);
        assertThat(applied.plan().message()).isEqualTo(answer.path("message").asString());
        assertThat(applied.plan().message()).doesNotContain("{count}", "{total}");
        assertThat(applied.plan().targets()).hasSize(answer.path("items").size());
        JsonNode history = json(expect(setup.hr().get(setup.chatPath()), 200));
        assertThat(history.get(0).path("answer").path("message")).isEqualTo(answer.path("message"));
        assertThat(history.get(0).path("answer").path("items")).isEqualTo(answer.path("items"));
    }

    private static ChatPlan find(Setup setup, SelectionMode mode) {
        return new ChatPlan(ChatPlan.Intent.FIND, mode, null, setup.ids(),
                "2명 중 **{count}명**으로 좁혔어요.", setup.ids().stream()
                        .map(id -> new ChatItem(id, "지원자", "Java Spring", "OK")).toList(),
                List.of("이력서"), List.of(), List.of());
    }

    private static JsonNode ask(Setup setup) throws Exception {
        return done(expect(setup.hr().post(setup.chatPath(),
                Map.of("message", "선택 요청", "mentionIds", List.of(), "checkedIds", List.of())), 200));
    }

    private Setup documentStage() throws Exception {
        TestApi hr = newHr();
        TestFixtures.Posting posting = TestFixtures.publish(hr, false);
        for (int number = 1; number <= 2; number++) {
            Map<String, Object> form = TestFixtures.form("applicant" + number + "@example.com", false);
            form.put("name", "지원자" + number);
            expect(anonymous().multipart(posting.applyPath(), form), 201);
        }
        UUID recruitmentId = UUID.fromString(posting.recruitmentId());
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (applications.applicants(hr.companyId(), recruitmentId).stream()
                .filter(applicant -> applicant.documentScore() != null).count() < 2
                && Instant.now().isBefore(deadline)) {
            Thread.sleep(200);
        }
        List<UUID> ids = applications.applicants(hr.companyId(), recruitmentId).stream()
                .map(applicant -> applicant.applicationId()).toList();
        // 필수 조건(중요 표시한 자격요건 Q-01 · Q-02)을 채워 두 지원자 모두 선 위에 둔다
        BigDecimal score = BigDecimal.valueOf(90);
        for (UUID id : ids) {
            applications.recordAnalysis(id, new ApplicationAnalysis(3, "OO카드", null, QualificationStatus.PASSED,
                    null, null, 50, null, 50, score, score, null, true, false, List.of(),
                    Map.of("Q-01", CriterionMark.MET, "Q-02", CriterionMark.MET)));
        }
        JsonNode closed = json(expect(hr.post("/api/recruitments/" + recruitmentId + "/posting/close", null), 200));
        UUID stageId = UUID.fromString(closed.path("stages").get(0).path("id").asString());
        return new Setup(hr, stageId, ids, TestFixtures.firstTab(hr, stageId));
    }

    private record Setup(TestApi hr, UUID stageId, List<UUID> ids, UUID tabId) {

        String chatPath() {
            return "/api/stages/" + stageId + "/tabs/" + tabId + "/chat";
        }

        String threadId() {
            return hr.companyId() + ":" + stageId + ":" + tabId;
        }
    }
}
