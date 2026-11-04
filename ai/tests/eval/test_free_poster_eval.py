"""무료 제공처 다운로드와 실제 로컬 모델의 도구 선택을 검증한다. LLM_EVAL=true일 때만 실행한다."""

import json

import pytest

from hiremate_ai.agents.generation.posting import design_poster
from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterDesign, PosterTurn
from hiremate_ai.config import settings
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때만 실제 모델을 사용한다")


class MemoryLog:
    def __init__(self) -> None:
        self.calls: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.calls.append(record)


async def test_search_select_and_change_layout_with_actual_model(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    log = MemoryLog()
    llm = build_llm(log)
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    result = await design_poster(llm, context, "외부 무료 SVG 템플릿 찾아줘")
    assert result.templates, (result.reply, [(call.status, call.error, call.output) for call in log.calls])
    assert all(item.license == "CC0 1.0" and "<svg" in item.svg for item in result.templates)
    context = context.model_copy(
        update={"history": [PosterTurn(role="ASSISTANT", text=result.reply, templates=result.templates)]}
    )
    selected = await design_poster(llm, context, "첫 번째 무료 템플릿으로 적용해줘")
    assert selected.selected_template_id == result.templates[0].id, selected.reply
    canvas = {
        "width": 600,
        "height": 1000,
        "objects": [
            {"hmId": "title", "binding": "title", "left": 40, "top": 60, "width": 500, "fontSize": 32, "text": ""},
            {
                "hmId": "benefits",
                "binding": "benefits",
                "left": 40,
                "top": 300,
                "width": 240,
                "fontSize": 14,
                "text": "",
            },
        ],
    }
    current = PosterDesign(
        template="CLASSIC",
        mood="TRUST",
        color="#112233",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
        canvas_json=json.dumps(canvas),
    )
    context = context.model_copy(update={"design": current, "history": []})
    edited = await design_poster(llm, context, "외부 포스터의 제목 글자 크기를 44로 하고 복지 영역을 오른쪽으로 옮겨줘")
    assert edited.recommendations, edited.reply
    updated = edited.recommendations[0].design
    assert updated.color == current.color
    assert updated.canvas_json
    elements = json.loads(updated.canvas_json)["objects"]
    assert elements[0]["fontSize"] == 44
    assert elements[1]["left"] > 40
    assert elements[0]["text"] == elements[1]["text"] == ""
