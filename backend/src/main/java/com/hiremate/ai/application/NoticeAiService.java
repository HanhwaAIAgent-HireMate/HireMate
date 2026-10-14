package com.hiremate.ai.application;

import com.hiremate.notice.NoticeDraftContext;
import com.hiremate.notice.NoticeGroup;
import com.hiremate.notice.NoticeService;
import com.hiremate.notice.NoticeStatus;
import com.hiremate.notice.NoticeView;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 안내 초안. 화면에서 바로 요청하는 작업이라 Root Agent를 거치지 않고 Communication Agent를 부른다. */
@Service
public class NoticeAiService {

    private final NoticeService notices;
    private final CommunicationAgent agent;
    private final AiSettings settings;

    public NoticeAiService(NoticeService notices, CommunicationAgent agent, AiSettings settings) {
        this.notices = notices;
        this.agent = agent;
        this.settings = settings;
    }

    /** 확정 결과로 그룹별 초안을 만들고, 내용이 빈 초안은 Communication Agent가 채운다. */
    public List<NoticeView> prepare(UUID companyId, UUID stageId) {
        for (NoticeView notice : notices.notices(companyId, stageId)) {
            if (notice.status() == NoticeStatus.DRAFT && notice.content().isBlank()) {
                NoticeDraftContext context = notices.draftContext(companyId, stageId, notice.group());
                notices.edit(companyId, stageId, notice.group(), notice.subject(), notice.greeting(),
                        agent.write(context, null).content(), notice.closing());
            }
        }
        return notices.notices(companyId, stageId);
    }

    /** 자연어 수정 요청. 수정안만 돌려주고 저장하지 않는다. HR이 적용하면 화면이 저장한다. */
    public NoticeAiAnswer revise(UUID companyId, UUID stageId, NoticeGroup group, String message) {
        CommunicationAgent.Draft draft = agent.write(notices.draftContext(companyId, stageId, group), message);
        return new NoticeAiAnswer(draft.reply(), draft.content(), "Communication Agent", settings.isStub());
    }

    public record NoticeAiAnswer(String reply, String content, String agent, boolean stub) {
    }
}
