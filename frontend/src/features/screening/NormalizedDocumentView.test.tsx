import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  codeLabel,
  matchEvidence,
  slots,
  visualSubject,
  type NormalizedDocument,
} from '@/features/screening/normalized'
import { NormalizedDocumentView } from '@/features/screening/NormalizedDocumentView'

const document: NormalizedDocument = {
  schemaVersion: '1.0',
  document: { id: 'doc', type: 'resume', title: null, pageCount: 2 },
  blocks: [
    {
      id: 'b1',
      type: 'section',
      title: 'ABOUT',
      pages: [1],
      blocks: [
        {
          id: 'b2',
          type: 'paragraph',
          pages: [1],
          text: '청구 접수, 보험사 전송, 제휴 정산 API와 배치를 개발했습니다.',
        },
      ],
    },
    {
      id: 'b3',
      type: 'section',
      title: 'SKILLS',
      pages: [1],
      blocks: [
        {
          id: 'b4',
          type: 'list',
          pages: [1],
          items: [
            { id: 'i1', text: 'Java 17', pages: [1], items: [] },
            { id: 'i2', text: 'Kafka', pages: [1], items: [] },
          ],
        },
      ],
    },
    {
      id: 'b5',
      type: 'table',
      pages: [2],
      title: '성과',
      headers: ['지표', '전', '후'],
      rows: [['p95', '1.2s', '140ms']],
    },
    {
      id: 'b6',
      type: 'visual_notice',
      pages: [2],
      visualType: 'diagram',
      message: '구조도는 원본 PDF에서 확인하세요.',
    },
  ],
}

describe('정제 문서(서류 원문) 보기', () => {
  it('JSON의 글을 빠짐없이 문단 · 목록 · 표로 그리고, 쪽이 바뀌는 곳에 쪽 번호를 단다', () => {
    const { container } = render(<NormalizedDocumentView document={document} />)

    for (const { text } of slots(document)) {
      expect(container.textContent).toContain(text)
    }
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('2쪽')).toBeInTheDocument()
    expect(screen.getByText('도식 · 구조도')).toBeInTheDocument()
  })

  it('시각 자료 안내는 자료 이름만 남긴다', () => {
    expect(
      visualSubject(
        '‘DLT 재처리 모니터링 화면 (사내 어드민)’ 자료는 텍스트로 확인할 수 없습니다. 원본 PDF에서 화면을 확인해 주세요.',
      ),
    ).toBe('‘DLT 재처리 모니터링 화면 (사내 어드민)’')
    expect(
      visualSubject(
        'seat-hold 전체 구조를 나타내는 자료가 포함되어 있을 수 있습니다. 원본 PDF에서 그림 1을 확인하세요.',
      ),
    ).toBe('seat-hold 전체 구조')
    expect(visualSubject('정산 관련 ERD와 주요 컬럼은 원본 PDF에서 확인하세요.')).toBe(
      '정산 관련 ERD와 주요 컬럼',
    )
    expect(visualSubject('그림 2의 매칭 알림 시퀀스를 확인하려면 원본 PDF를 참고하세요.')).toBe(
      '그림 2의 매칭 알림 시퀀스',
    )
  })

  it('코드 종류: 명령어와 폴더 구조가 섞이면 둘 다 적고, 단계 주석은 설명으로 쓰지 않는다', () => {
    expect(
      codeLabel('# 1. 인프라 실행\ndocker compose up -d\nseat-hold/\n├── seat-api/\n└── common/'),
    ).toEqual({ kind: '실행 명령어 · 폴더 구조', note: '' })
    expect(codeLabel('-- 1) 자연키 유니크 제약\nALTER TABLE trade ADD CONSTRAINT uq;')).toEqual({
      kind: 'SQL',
      note: '1) 자연키 유니크 제약',
    })
  })

  it('PDF 글의 근거도 가운뎃점 · 띄어쓰기가 달라도 찾아 밑줄을 긋는다', () => {
    const sentence = '청구 접수·보험사 전송·제휴 정산 API와 배치를 개발했습니다.'
    const { spans, unmatched } = matchEvidence(document, [sentence])
    const { container } = render(<NormalizedDocumentView document={document} spans={spans} />)

    expect(unmatched).toEqual([])
    expect(container.querySelector('mark')?.textContent).toBe(
      '청구 접수, 보험사 전송, 제휴 정산 API와 배치를 개발했습니다',
    )
  })

  it('코드는 그리지 않고 어떤 코드인지만 알리며, 짝인 줄바꿈 안내는 따로 보이지 않는다', () => {
    const withCode: NormalizedDocument = {
      ...document,
      blocks: [
        {
          id: 'c1',
          type: 'section',
          title: '핵심 코드',
          pages: [1],
          blocks: [
            {
              id: 'c2',
              type: 'paragraph',
              pages: [1],
              text: '// 청구 목록: no-offset 페이지네이션\npublic List<Claim> findClaims(Long id) {\n    return query;\n}',
            },
            {
              id: 'c3',
              type: 'visual_notice',
              pages: [1],
              visualType: 'unknown',
              message: '코드의 줄바꿈과 들여쓰기는 원본 PDF에서 확인해 주세요.',
            },
          ],
        },
      ],
    }
    const { container } = render(<NormalizedDocumentView document={withCode} />)

    expect(
      screen.getByText('코드 · Java 코드 — 청구 목록: no-offset 페이지네이션'),
    ).toBeInTheDocument()
    expect(container.textContent).not.toContain('findClaims')
    expect(container.textContent).not.toContain('들여쓰기')
    // 근거가 코드 안에 있으면 코드 글은 그대로 숨기고 안내에 밑줄을 긋는다
    const { spans, unmatched } = matchEvidence(withCode, ['return query;'])
    const cited = render(<NormalizedDocumentView document={withCode} spans={spans} />)
    expect(unmatched).toEqual([])
    expect(cited.container.querySelector('mark')?.textContent).toContain(
      '근거가 이 코드 안에 있어요',
    )
    expect(cited.container.textContent).not.toContain('return query')
  })

  it('칸을 넘어 이어진 근거는 칸마다 밑줄을 긋고, 없는 문장은 찾지 못한 근거로 돌려준다', () => {
    const { spans, unmatched } = matchEvidence(document, [
      'Java 17 Kafka',
      '지원자가 쓰지 않은 문장입니다',
    ])

    expect(spans.get('i1:text')).toEqual([{ start: 0, end: 7 }])
    expect(spans.get('i2:text')).toEqual([{ start: 0, end: 5 }])
    expect(unmatched).toEqual(['지원자가 쓰지 않은 문장입니다'])
  })
})
