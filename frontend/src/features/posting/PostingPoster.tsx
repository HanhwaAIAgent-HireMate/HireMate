import { ArrowUpRight, Check, Coffee, Sparkles } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import type { Posting } from '@/features/posting/api'
import { conditionRows } from '@/features/posting/conditions'
import { posterPalette, posterTagline, type PosterDesign } from '@/features/posting/poster-design'
import type { PosterChanges } from './poster-preview'
import { formatDateTime } from '@/lib/format'
import type { StageIconName } from '@/features/recruit/StageIcon'
import type { StageType } from '@/features/recruit/labels'
import { StageProcess } from '@/features/recruit/StageProcess'
import { CanvasPoster } from '@/features/posting/CanvasPoster'
import { PosterMotion } from './PosterMotion'
import { preparePosterLogo } from '@/features/posting/poster-canvas'

import './posting-poster.css'
import '@fontsource-variable/noto-sans-kr'

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
  changes,
}: {
  posting: PosterPosting
  design: PosterDesign
  logoUrl?: string
  careersUrl?: string
  compact?: boolean
  sectionIds?: boolean
  changes?: PosterChanges
}) {
  const content = posting.content
  const hasLogo = Boolean(design.showLogo && design.logoFileId && logoUrl)
  const logoKey = `${logoUrl}:${design.color}`
  const [logoMetrics, setLogoMetrics] = useState<{
    source: string
    wordmark: boolean
    image: string
  } | null>(null)
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
          highlightedNames={changes?.stages}
        />
      ),
    })
  if (posting.documents.length)
    blocks.push({
      label: '제출 서류',
      kind: 'documents',
      children: (
        <ul className="poster-document-list">
          {posting.documents.map((document) => (
            <li key={document.type}>
              <span>
                {document.label}
                {document.format === 'PDF' && ' PDF'}
              </span>{' '}
              <small>{document.required ? '필수' : '선택'}</small>
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
  if (design.canvasJson)
    return (
      <CanvasPoster
        posting={posting}
        design={design}
        logoUrl={logoUrl}
        sectionIds={sectionIds}
        changes={changes}
        compact={compact}
      />
    )
  return (
    <article
      className={`posting-poster${compact ? 'poster-compact' : ''}`}
      data-template={design.template}
      data-mood={design.mood}
      data-decoration={design.decoration}
      data-background={design.backgroundStyle ?? 'SOLID'}
      data-has-logo={hasLogo}
      data-wordmark={hasLogo && logoMetrics?.wordmark === true && logoMetrics.source === logoKey}
      style={posterPalette(design.color)}
      aria-label={`${posting.companyName} ${content.title} 채용 포스터`}
      data-poster-highlight={changes?.all || undefined}
    >
      <header
        className="poster-hero"
        data-poster-highlight={changes?.bindings.includes('header-motion') || undefined}
      >
        {!compact && <PosterMotion effect={design.motion} />}
        <div className="poster-brand">
          <span>
            {design.showLogo && design.logoFileId && logoUrl && (
              <img
                src={logoMetrics?.source === logoKey ? logoMetrics.image : logoUrl}
                alt={`${posting.companyName} 로고`}
                onLoad={(event) => {
                  const image = event.currentTarget
                  if (image.src.startsWith('data:')) return
                  const canvas = document.createElement('canvas')
                  const ratio = Math.min(
                    1,
                    1600 / Math.max(image.naturalWidth, image.naturalHeight),
                  )
                  canvas.width = Math.max(1, Math.round(image.naturalWidth * ratio))
                  canvas.height = Math.max(1, Math.round(image.naturalHeight * ratio))
                  canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height)
                  let processed = logoUrl
                  try {
                    processed = preparePosterLogo(canvas, design.color).toDataURL('image/png')
                  } catch {
                    /* 원본을 표시한다. */
                  }
                  setLogoMetrics({
                    source: logoKey,
                    wordmark: image.naturalWidth / Math.max(1, image.naturalHeight) > 2.2,
                    image: processed,
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
        <small
          className="poster-eyebrow"
          data-poster-highlight={changes?.bindings.includes('tagline') || undefined}
        >
          {posterTagline(posting, design)}
        </small>
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
              data-poster-highlight={changes?.bindings.includes(block.kind) || undefined}
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
