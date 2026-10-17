package com.hiremate.ai.infra;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AiModeConditionTests {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(StubRoot.class, RemoteRoot.class, StubReport.class, RemoteReport.class);

    @Test
    @DisplayName("설정이 없으면 모든 Agent가 stub이다")
    void defaultsToStub() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(StubRoot.class).doesNotHaveBean(RemoteRoot.class);
            assertThat(context).hasSingleBean(StubReport.class).doesNotHaveBean(RemoteReport.class);
        });
    }

    @Test
    @DisplayName("hiremate.ai.mode는 모든 Agent의 기본값이다")
    void followsGlobalMode() {
        runner.withPropertyValues("hiremate.ai.mode=remote").run(context -> {
            assertThat(context).hasSingleBean(RemoteRoot.class).doesNotHaveBean(StubRoot.class);
            assertThat(context).hasSingleBean(RemoteReport.class).doesNotHaveBean(StubReport.class);
        });
    }

    @Test
    @DisplayName("한 Agent만 remote로 바꿔도 다른 Agent는 stub을 쓴다")
    void overridesPerAgent() {
        runner.withPropertyValues("hiremate.ai.mode=stub", "hiremate.ai.agents.root=remote").run(context -> {
            assertThat(context).hasSingleBean(RemoteRoot.class).doesNotHaveBean(StubRoot.class);
            assertThat(context).hasSingleBean(StubReport.class).doesNotHaveBean(RemoteReport.class);
        });
    }

    @Test
    @DisplayName("모르는 연동 방식이면 앱을 띄우지 않는다")
    void rejectsUnknownMode() {
        runner.withPropertyValues("hiremate.ai.agents.report=local").run(context ->
                assertThat(context).hasFailed());
    }

    @ConditionalOnAiMode(agent = AiAgent.ROOT, mode = AiMode.STUB)
    static class StubRoot {
    }

    @ConditionalOnAiMode(agent = AiAgent.ROOT, mode = AiMode.REMOTE)
    static class RemoteRoot {
    }

    @ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.STUB)
    static class StubReport {
    }

    @ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.REMOTE)
    static class RemoteReport {
    }
}
