"""도구의 조회 범위. 여러 Agent의 도구가 같이 쓴다."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ToolScope:
    """도구가 ToolRuntime[ToolScope]의 runtime.context로 받는 조회 범위. 값은 코드가 넣고 모델이 바꿀 수 없다 (규칙 4).

    도구는 인자로 받은 지원자 id가 application_ids에 없으면 자료를 주지 않는다.
    """

    company_id: UUID
    recruitment_id: UUID
    stage_id: UUID
    application_ids: frozenset[UUID]  # 현재 전형 지원자
