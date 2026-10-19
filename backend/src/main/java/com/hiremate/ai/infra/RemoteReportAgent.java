package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.ReportAgent;
import com.hiremate.ai.application.ReportInput;
import com.hiremate.report.ReportContent;
import java.util.Map;
import org.springframework.stereotype.Component;

/** ai 서버의 Report Agent. 인원과 숫자는 ai 서버가 입력 값을 그대로 옮기고, 합격 근거와 특이사항 문장만 모델이 쓴다. */
@Component
@ConditionalOnAiMode(agent = AiAgent.REPORT, mode = AiMode.REMOTE)
class RemoteReportAgent implements ReportAgent {

    private final AiServerClient client;

    RemoteReportAgent(AiServerClient client) {
        this.client = client;
    }

    @Override
    public ReportContent write(ReportInput input) {
        return client.post(AiAgent.REPORT, "write", Map.of("input", input), ReportContent.class);
    }
}
