"""근거 번호표. 도구가 돌려준 근거 한 줄마다 이번 요청의 번호(E1, E2, …)를 붙이고 올릴 수 있는 최고 상태를 기억한다.

모델은 원문을 옮겨 쓰지 않고 번호로 인용한다. 번호표는 요청 하나 동안만 쓰고 대화방에 저장하지 않는다.
"""

from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID

from hiremate_ai.contract import InterviewerMemo

type Cap = Literal["OK", "CHECK"]

_CAP_LABELS: dict[Cap, str] = {"OK": "근거 확인", "CHECK": "확인 필요"}


@dataclass(frozen=True)
class Evidence:
    ref: str
    application_id: UUID | None  # 공통 사실(전형 집계, 회사, 공고)은 None
    text: str  # 정리한 내용
    quote: str | None  # 원문 문장
    source: str  # 이력서, 자기소개서, 전형 결과, 회사 소개, 공고, 면접 기록, 면접관메모, 앞 대화 답변 등
    cap: Cap  # 올릴 수 있는 최고 상태
    agent: str | None = None  # 근거를 정리한 분석 Agent (예: Application Agent)
    memo: InterviewerMemo | None = None  # 면접관메모 근거면 원본


@dataclass
class Ledger:
    _items: dict[str, Evidence] = field(default_factory=dict)
    _keys: dict[tuple[UUID | None, str, str | None, str], str] = field(default_factory=dict)

    def add(
        self,
        application_id: UUID | None,
        text: str,
        *,
        source: str,
        cap: Cap,
        quote: str | None = None,
        agent: str | None = None,
        memo: InterviewerMemo | None = None,
    ) -> str:
        """같은 근거를 다시 넣으면 번호를 유지하고 상태는 낮은 쪽(CHECK)으로 둔다."""
        key = (application_id, text, quote, source)
        ref = self._keys.get(key)
        if ref is not None:
            if cap == "CHECK":
                self._items[ref] = replace(self._items[ref], cap="CHECK")
            return ref
        ref = f"E{len(self._items) + 1}"
        self._keys[key] = ref
        self._items[ref] = Evidence(ref, application_id, text, quote, source, cap, agent, memo)
        return ref

    def get(self, ref: str) -> Evidence | None:
        return self._items.get(ref)

    def line(self, ref: str) -> str:
        """E1 [근거 확인] 내용 — 근거: "원문" (출처)"""
        evidence = self._items[ref]
        quoted = f' — 근거: "{evidence.quote}"' if evidence.quote else ""
        return f"{ref} [{_CAP_LABELS[evidence.cap]}] {evidence.text}{quoted} ({evidence.source})"
