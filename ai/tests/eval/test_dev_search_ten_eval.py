"""고정된 가상 지원자 10명으로 검색 후보와 판정 변동을 실제 모델에 평가한다."""

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.extract import ExtractedFacts
from hiremate_ai.agents.root.find import CriteriaResult, RecheckItem, RecheckResult
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import ToolAgent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch
from hiremate_ai.tools.scope import ToolScope

HERE = Path(__file__).parent
GOLD: dict[str, Any] = json.loads((HERE / "dev_search_ten_gold.json").read_text(encoding="utf-8"))
REVIEWS: dict[str, Any] = json.loads((HERE / "dev_search_ten_reviews.json").read_text(encoding="utf-8"))
FINANCE = {
    "id": "finance-work",
    "query": "금융 서비스 개발 실무 경험이 있는 지원자를 찾아줘",
    "must_include": {"이재희": "", "강혜원": "", "김다인": "", "김하늘": ""},
    "must_exclude": {"이도윤": ""},
}


class Metrics:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


async def test_judgment_trace_captures_numbered_reply_and_input() -> None:
    result = RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[2])])
    observer = JudgmentObserver(FakeLlm(result))

    actual = await observer.structured(RecheckResult, agent="root", system="system", user="candidate evidence")

    assert actual == result
    assert observer.judgments[0]["input"] == "candidate evidence"
    assert observer.judgments[0]["result"] == result.model_dump(mode="json")


class ExtractionObserver:
    def __init__(self, client: LlmClient) -> None:
        self.client = client
        self.first: list[ExtractedFacts] = []

    def analysis_recipe(self) -> dict[str, Any] | None:
        return self.client.analysis_recipe()

    async def structured[T: BaseModel](
        self, output: type[T], *, agent: str, system: str, user: str, images: Sequence[str] = ()
    ) -> T:
        result = await self.client.structured(output, agent=agent, system=system, user=user, images=images)
        if isinstance(result, ExtractedFacts):
            self.first.append(result)
        return result

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
        forms: Mapping[str, type[BaseModel]] | None = None,
        max_calls: int | None = None,
    ) -> ToolAgent[T]:
        return self.client.tool_agent(
            output, agent=agent, system=system, tools=tools, context=context, forms=forms, max_calls=max_calls
        )


class JudgmentObserver(ExtractionObserver):
    def __init__(self, client: LlmClient) -> None:
        super().__init__(client)
        self.judgments: list[dict[str, Any]] = []

    async def structured[T: BaseModel](
        self, output: type[T], *, agent: str, system: str, user: str, images: Sequence[str] = ()
    ) -> T:
        result = await super().structured(output, agent=agent, system=system, user=user, images=images)
        if isinstance(result, RecheckResult | CriteriaResult):
            self.judgments.append(
                {
                    "input": user,
                    "input_sha256": sha256(user.encode()).hexdigest(),
                    "result": result.model_dump(mode="json"),
                }
            )
        return result


def capture_search(search: CandidateSearch, captured: list[CandidateMatch]) -> CandidateSearch:
    async def capture(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        found = await search(scope, concepts, pool)
        captured.extend(found)
        return found

    return capture
