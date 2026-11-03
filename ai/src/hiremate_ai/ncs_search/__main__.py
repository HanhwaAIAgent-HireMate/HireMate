"""질의 임베딩 서비스 실행. ai 폴더에서: uv run --group ncs python -m hiremate_ai.ncs_search

ai 서버와 같은 설정(ai/.env)을 쓰고 따로 띄운다. 모델을 처음 받으면 시간이 걸린다.
"""

import uvicorn

from hiremate_ai.config import settings
from hiremate_ai.ncs_search.embedder import BgeM3Embedder
from hiremate_ai.ncs_search.service import create_app


def main() -> None:
    app = create_app(BgeM3Embedder(settings.ncs_model, settings.ncs_device))
    uvicorn.run(app, host=settings.ncs_embed_host, port=settings.ncs_embed_port)


if __name__ == "__main__":
    main()
