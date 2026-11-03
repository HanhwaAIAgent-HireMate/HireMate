import { ArrowUpRight, Check, Coffee, Sparkles } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import type { Posting } from '@/features/posting/api'
import { conditionRows } from '@/features/posting/conditions'
import { posterPalette, type PosterDesign } from '@/features/posting/poster-design'
import { formatDateTime } from '@/lib/format'
import type { StageIconName } from '@/features/recruit/StageIcon'
import type { StageType } from '@/features/recruit/labels'
import { StageProcess } from '@/features/recruit/StageProcess'

import './posting-poster.css'

export type PosterPosting = Pick<
  Posting,
  'companyName' | 'content' | 'notices' | 'documents' | 'openAt' | 'closeAt'
> & { stages: { name: string; type?: StageType; icon?: StageIconName | null }[] }

/** 편집/지원자 페이지/PDF가 모두 같은 데이터와 컴포넌트를 사용한다. */
export function PostingPoster({
  posting,
  design,
  logoUrl,
  careersUrl,
  compact = false,
  sectionIds = false,
}: {
  posting: PosterPosting
  design: PosterDesign
  logoUrl?: string
  careersUrl?: string
  compact?: boolean
  sectionIds?: boolean
}) {
  const content = posting.content
  const hasLogo = Boolean(design.showLogo && design.logoFileId && logoUrl)
  const [logoMetrics, setLogoMetrics] = useState<{ source: string; wordmark: boolean } | null>(null)
  const conditions = [
    { label: '고용 형태', value: content.employmentType },
    { label: '경력', value: content.career },
    { label: '근무지', value: content.location },
    ...conditionRows(content),
  ].filter((row) => row.value)
  const blocks: { label: string; kind: string; children: ReactNode }[] = []
  if (content.intro.trim())
    blocks.push({ label: '회사 소개', kind: 'intro', children: <p>{content.intro}</p> })
  for (const [key, label] of [
    ['duties', '주요 업무'],
    ['qualifications', '자격 요건'],
    ['preferred', '우대 사항'],
    ['benefits', '복지 및 혜택'],
  ] as const) {
    if (content[key].length)
      blocks.push({
        label,
        kind: key,
        children: (
          <ul>
            {content[key].map((line, index) => (
              <li key={`${index}-${line}`}>
                {key === 'benefits' && <Coffee aria-hidden="true" />}
                {line}
              </li>
            ))}
          </ul>
        ),
      })
  }
  if (posting.stages.length)
    blocks.push({
      label: '전형 절차',
      kind: 'stages',
      children: (
        <StageProcess
          includeFinal
          stages={posting.stages.map((stage) => ({
            ...stage,
            icon: design.stageIcons?.[stage.name] ?? 'AUTO',
          }))}
          color={design.color}
        />
      ),
    })
  if (posting.documents.length)
    blocks.push({
      label: '제출 서류',
      kind: 'documents',
      children: (
        <ul>
          {posting.documents.map((document) => (
            <li key={document.type}>
              {document.label}
              {document.format === 'PDF' && ' PDF'} · {document.required ? '필수' : '선택'}
            </li>
          ))}
        </ul>
      ),
    })
  if (posting.notices.length)
    blocks.push({
      label: '유의사항',
      kind: 'notices',
      children: (
        <ul>
          {posting.notices.map((line, index) => (
            <li key={`${index}-${line}`}>{line}</li>
          ))}
        </ul>
      ),
    })
  return (
    <article
      className={`posting-poster${compact ? 'poster-compact' : ''}`}
      data-template={design.template}
      data-mood={design.mood}
      data-decoration={design.decoration}
      data-background={design.backgroundStyle ?? 'SOLID'}
      data-has-logo={hasLogo}
      data-wordmark={hasLogo && logoMetrics?.wordmark === true && logoMetrics.source === logoUrl}
      style={posterPalette(design.color)}
      aria-label={`${posting.companyName} ${content.title} 채용 포스터`}
    >
      <header className="poster-hero">
        <div className="poster-brand">
          <span>
            {design.showLogo && design.logoFileId && logoUrl && (
              <img
                src={logoUrl}
                alt={`${posting.companyName} 로고`}
                onLoad={(event) => {
                  const image = event.currentTarget
                  setLogoMetrics({
                    source: logoUrl,
                    wordmark: image.naturalWidth / Math.max(1, image.naturalHeight) > 2.2,
                  })
                }}
              />
            )}
            <strong>{posting.companyName}</strong>
          </span>
          <small>CAREERS</small>
        </div>
        <div className="poster-decoration" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
        <small className="poster-eyebrow">함께할 동료를 찾습니다</small>
        <h2>{content.title || '채용 공고'}</h2>
        <div className="poster-tags">
          {[content.jobCategory, content.employmentType, content.career]
            .filter(Boolean)
            .map((tag, index) => (
              <span key={`${index}-${tag}`}>{tag}</span>
            ))}
        </div>
      </header>
      <div className="poster-body">
        {conditions.length > 0 && (
          <dl className="poster-conditions">
            {conditions.map((row) => (
              <div className="poster-condition" key={row.label}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
        <div className="poster-sections">
          {blocks.map((block, index) => (
            <section
              id={
                sectionIds
                  ? ({ intro: 'company', benefits: 'benefits' } as Record<string, string>)[
                      block.kind
                    ]
                  : undefined
              }
              className={`poster-block poster-block-${block.kind}`}
              key={block.kind}
              data-readable={design.readableSections?.includes(index + 1) ?? false}
            >
              <div className="poster-section-title">
                <span className="poster-number">{String(index + 1).padStart(2, '0')}</span>
                <h3>
                  {block.kind === 'benefits' && <Sparkles aria-hidden="true" />}
                  {block.label}
                </h3>
                <Check className="poster-check" aria-hidden="true" />
              </div>
              <div className="poster-block-content">{block.children}</div>
            </section>
          ))}
        </div>
      </div>
      {(careersUrl || (posting.openAt && posting.closeAt)) && (
        <footer className="poster-footer">
          {posting.openAt && posting.closeAt && (
            <div>
              <small>접수 기간</small>
              <span>{`${formatDateTime(posting.openAt)} ~ ${formatDateTime(posting.closeAt)}`}</span>
            </div>
          )}
          {careersUrl && (
            <a className="poster-careers-link" href={careersUrl} target="_blank" rel="noreferrer">
              채용 공고 바로가기 <ArrowUpRight aria-hidden="true" />
            </a>
          )}
        </footer>
      )}
    </article>
  )
}
