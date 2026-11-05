"""지정한 기업과 채용의 기존 프로필을 내부 임베딩 서비스로 색인한다."""

import argparse
import asyncio
from uuid import UUID

from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.tools.profile_search import backfill_profile_embeddings, get_profile_embedder


def main() -> None:
    parser = argparse.ArgumentParser(description="기존 지원자 프로필의 임베딩을 채운다")
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--recruitment-id", type=UUID, required=True)
    args = parser.parse_args()
    asyncio.run(backfill(args.company_id, args.recruitment_id))


async def backfill(company_id: UUID, recruitment_id: UUID) -> None:
    count = await backfill_profile_embeddings(
        session_factory(), get_profile_embedder(), company_id, recruitment_id, model=settings.ncs_model
    )
    print(f"프로필 {count}개 색인을 확인했습니다.")


if __name__ == "__main__":
    main()
