import { useEffect, useRef, useState } from 'react'

import type { PosterDesign } from '@/features/posting/poster-design'
import { PostingPoster, type PosterPosting } from '@/features/posting/PostingPoster'

/** 고정 영역 안에 포스터 전체를 맞춘다. fill은 카드의 바깥 여백만 없앤다. */
export function PosterThumbnail({
  posting,
  design,
  logoUrl,
  compact = false,
  fill = false,
}: {
  posting: PosterPosting
  design: PosterDesign
  logoUrl?: string
  compact?: boolean
  fill?: boolean
}) {
  const host = useRef<HTMLDivElement>(null)
  const paper = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.15)
  const thumbnailPosting: PosterPosting = {
    ...posting,
    content: {
      ...posting.content,
      intro: '',
      duties: posting.content.duties.slice(0, 1),
      qualifications: posting.content.qualifications.slice(0, 1),
      preferred: [],
      benefits: posting.content.benefits.slice(0, 1),
      headcount: null,
      position: '',
      education: '',
      workHours: '',
      salary: '',
    },
    stages: posting.stages.slice(0, 2),
    documents: [],
    notices: [],
  }
  useEffect(() => {
    const hostElement = host.current
    const paperElement = paper.current
    if (!hostElement || !paperElement) return
    const observer = new ResizeObserver(() => {
      const padding = fill ? 0 : 16
      const widthScale = (hostElement.clientWidth - padding) / 600
      const heightScale =
        (hostElement.clientHeight - padding) / Math.max(1, paperElement.offsetHeight)
      setScale(Math.min(widthScale, heightScale))
    })
    observer.observe(hostElement)
    observer.observe(paperElement)
    return () => observer.disconnect()
  }, [fill])
  return (
    <div
      ref={host}
      className={`pointer-events-none relative w-full shrink-0 overflow-hidden ${fill ? 'bg-background' : 'bg-surface'} ${compact ? 'h-24' : 'h-48'}`}
      aria-hidden="true"
    >
      <div
        ref={paper}
        className={`absolute left-1/2 w-[600px] origin-top ${fill ? 'top-0' : 'top-2'}`}
        style={{ transform: `translateX(-50%) scale(${scale})` }}
      >
        <PostingPoster
          posting={thumbnailPosting}
          design={{ ...design, motion: 'NONE' }}
          logoUrl={logoUrl}
        />
      </div>
    </div>
  )
}
