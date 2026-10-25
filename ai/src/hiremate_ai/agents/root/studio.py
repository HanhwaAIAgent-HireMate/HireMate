"""LangSmith Studio에 올리는 Root 그래프. ai 폴더에서 `uv run langgraph dev`로 연다 (ai/langgraph.json).

ai 서버는 이 모듈을 쓰지 않는다. 모델은 ai/.env 설정을 쓰고, 지원자 자료는 DB 없이 ChatContext 문서로 읽는다.
실행 context의 기본값이 가상 지원자 샘플(contract/ChatContext.json)이라 Studio에서는 message만 바꿔 넣으면 된다.
message의 @이름은 화면에서 @로 고른 지원자처럼 mentions가 된다.
"""

from pathlib import Path
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter, create_model, model_validator

from hiremate_ai.agents.root.graph import RootState, build_root_graph
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.types import CandidateRow, ChatContext
from hiremate_ai.llm.client import get_llm

SAMPLE_PATH = Path(__file__).resolve().parents[5] / "contract" / "ChatContext.json"
SAMPLE = ChatContext.model_validate_json(SAMPLE_PATH.read_bytes())
_ROWS = TypeAdapter(list[CandidateRow])


class _MentionsFromMessage(ChatContext):
    @model_validator(mode="before")
    @classmethod
    def _mentions(cls, data: Any) -> Any:
        """Studio가 보낸 mentions는 쓰지 않고 message의 @이름으로 다시 정한다."""
        if not isinstance(data, dict):
            return data
        message = str(data.get("message", SAMPLE.message))
        rows = _ROWS.validate_python(data["candidates"]) if "candidates" in data else SAMPLE.candidates
        return {**data, "mentions": [row.application_id for row in rows if f"@{row.name}" in message]}


_fields: dict[str, Any] = {
    name: (info.annotation, getattr(SAMPLE, name)) for name, info in ChatContext.model_fields.items()
}
StudioContext = create_model("StudioContext", __base__=_MentionsFromMessage, **_fields)
"""모든 필드의 기본값이 샘플인 ChatContext. Studio가 보낸 값만 샘플 위에 덮어쓴다."""


def make_graph() -> CompiledStateGraph[RootState, ChatContext, RootState, RootState]:
    """langgraph.json이 부르는 그래프 팩토리. 대화방 저장은 Studio 서버의 체크포인터가 맡는다."""
    return build_root_graph(get_llm(), default_toolkit(), context_schema=StudioContext)
