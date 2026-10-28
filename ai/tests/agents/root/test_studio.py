import json
from pathlib import Path
from typing import Any

from root_context import form_call

from hiremate_ai.agents.root import studio
from hiremate_ai.agents.root.graph import build_root_graph
from hiremate_ai.agents.root.studio import SAMPLE, StudioContext
from hiremate_ai.agents.root.types import ChatContext, EditAction, Intent
from hiremate_ai.llm.fake import FakeLlm

AI_DIR = Path(__file__).resolve().parents[3]


def ids(context: ChatContext, *names: str) -> list[object]:
    by_name = {row.name: row.application_id for row in context.candidates}
    return [by_name[name] for name in names]


def test_context_defaults_to_sample_and_mentions_follow_message() -> None:
    context = StudioContext.model_validate({"message": "@윤태오 강점 알려줘"})

    assert isinstance(context, ChatContext)
    assert context.candidates == SAMPLE.candidates
    assert context.mentions == ids(SAMPLE, "윤태오")
    assert StudioContext.model_validate({"message": "강점 요약해줘"}).mentions == []
    # Studio가 샘플의 mentions를 그대로 보내도 message를 따른다
    sent = {"message": "@윤태오 빼줘", "mentions": [str(id) for id in ids(SAMPLE, "정유민")]}
    assert StudioContext.model_validate(sent).mentions == ids(SAMPLE, "윤태오")


async def test_graph_takes_only_message_as_context() -> None:
    graph = build_root_graph(
        FakeLlm(form_call("edit", action="CLEAR", scope={})),
        context_schema=StudioContext,
    )

    # Studio는 context를 JSON 객체로 보내고, 그래프가 context_schema로 바꾼다
    sent: Any = {"message": "선택 지원자 비워줘"}
    state = await graph.ainvoke({}, context=sent)

    plan = state["turns"][-1]["plan"]
    assert (plan["intent"], plan["edit"]) == (Intent.EDIT, EditAction.CLEAR)


def test_langgraph_json_points_to_factory() -> None:
    spec = json.loads((AI_DIR / "langgraph.json").read_text(encoding="utf-8"))
    path, name = spec["graphs"]["root"].split(":")

    assert (AI_DIR / path).resolve() == Path(studio.__file__).resolve()
    assert callable(getattr(studio, name))
