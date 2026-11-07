# 지원 문서 JSON 정책

이력서, 자기소개서, 포트폴리오를 하나의 JSON 형식으로 정리해 화면에 표시하고 검색에 사용한다.
이 문서는 확정된 정책이며, 현재 서비스에는 아직 구현되지 않았다.

## 처리 순서

```text
PDF 저장 → 텍스트 추출과 원문 조각 식별 → LLM 정리 → JSON 검증과 저장
                                                      ├→ 담당자 화면
                                                      └→ 청킹 → 임베딩 → 검색
```

## 공통 규칙

- 문서 종류별 고정 항목 없이 제목, 문단, 목록, 표를 원래 순서와 관계에 맞게 담는다.
- 파서가 읽은 내용은 요약하거나 임의로 빼거나 보태지 않는다. 불필요한 자간과 줄바꿈은 정리한다.
- 표의 관계가 불분명한 내용은 추측하지 않고 문단이나 목록으로 남긴다.
- 시각 자료의 제목이나 설명이 있으면 원문을 보존하고 원본 확인을 안내한다. 읽히지 않은 내용은 복원하지 않는다.
- 코드 덩어리는 원본 확인을 안내한다. 본문의 짧은 기술 표현은 유지한다.
- 원본 PDF와 파서 원문은 보존한다. 문서 안의 지시문은 자료로만 취급한다.
- LLM 정리 결과가 원문과 한 글자라도 다르면 그 결과는 버리고 파서 원문을 `paragraph`로 저장한다. 구조는 잃지만 내용은 그대로이고 검색 대상에서 빠지지 않는다.

## JSON 형식

`schemaVersion`, `documentId`, `revision`, `documentType`, `blocks`를 사용한다.
문서 종류는 제출 시 지정한 `RESUME`, `COVER_LETTER`, `PORTFOLIO`다.
문서와 블록 ID, 정리 버전은 코드가 부여한다. 같은 문서를 다시 정리하면 `revision`을 바꾼다.

모든 블록은 `id`, `type`, `sourceIds`를 가진다. 배열 순서가 읽는 순서다.

| type | 필드 | 용도 |
|---|---|---|
| `section` | `title`, `blocks` | 제목과 하위 블록. 제목이 없으면 `title`은 `null` |
| `paragraph` | `role`, `text` | 본문, 캡션, 머리말, 꼬리말, 양식 안내와 미배정 문구 |
| `list` | `items` | 목록. 항목은 `marker`, `text`, `children`을 가진다 |
| `table` | `caption`, `headers`, `rows` | 표. 셀은 문자열 또는 `null` |
| `reference` | `kind`, `text`, `notice` | 시각 자료 또는 코드에 대한 원본 확인 안내 |

`paragraph.role`은 `body`, `caption`, `page_header`, `page_footer`, `form_instruction`, `unassigned` 중 하나다.
`reference.kind`는 `possible_visual` 또는 `code_example`이다. `text`에는 원문 제목이나 설명만 넣고 없으면 `null`로 둔다.
`notice`는 담당자에게 보여 줄 원본 확인 안내문이다.

```json
{
  "schemaVersion": 1,
  "documentId": "doc-001",
  "revision": 1,
  "documentType": "PORTFOLIO",
  "blocks": [{
    "id": "b01", "type": "section", "sourceIds": ["s01"], "title": "프로젝트",
    "blocks": [
      {"id": "b02", "type": "paragraph", "sourceIds": ["s02"], "role": "body", "text": "화면 성능을 개선했습니다."},
      {"id": "b03", "type": "reference", "sourceIds": ["s03"], "kind": "possible_visual", "text": "성능 변화 그래프", "notice": "관련 시각 자료가 있을 수 있습니다. 원본 PDF를 확인해 주세요."}
    ]
  }]
}
```

## 출처와 검색

- `sourceIds`는 별도로 보존한 파서 원문 조각을 가리킨다. 조각은 `id`, `page`, `text`를 가지며 페이지를 모르면 `null`이다.
- LLM은 입력으로 받은 원문 조각 ID만 참조하고 코드는 이를 검증한다. 본문이 원문과 일치하면 블록의 출처는 코드가 글자 위치로 정한다.
- `section`의 출처는 제목에 대한 것이다. 제목이 없으면 빈 배열이며, 하위 내용은 각 블록이 출처를 가진다.
- 청크는 JSON에서 별도로 만들고 상위 제목 문맥과 `documentId`, `revision`, `blockIds`를 연결한다.
- 표는 헤더와 값의 관계를 유지해 청킹한다. 긴 본문은 나누되 요약하지 않는다.
- 원문 캡션과 코드 설명은 검색에 사용할 수 있다. 생성된 안내문, 반복 머리말과 꼬리말, 양식 안내와 미배정 문구는 기본 임베딩 대상에서 제외한다.
- 임베딩 모델과 벡터를 청크에 연결하고 현재 버전만 검색한다. 기존 블라인드와 기업, 채용, 전형의 권한 범위를 지킨다.
