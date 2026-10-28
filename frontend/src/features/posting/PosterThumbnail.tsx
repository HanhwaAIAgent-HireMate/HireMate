import { useEffect, useRef, useState } from 'react'

import type { PosterDesign } from '@/features/posting/poster-design'
import { PostingPoster, type PosterPosting } from '@/features/posting/PostingPoster'

/** 긴 공고도 상단만 잘라 보이지 않도록 포스터 전체를 썸네일 안에 맞춘다. */
export function PosterThumbnail({
  posting,
  design,
  logoUrl,
  compact = false,
}: {
  posting: PosterPosting
  design: PosterDesign
  logoUrl?: string
  compact?: boolean
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
      setScale(
        Math.min(
          (hostElement.clientWidth - 16) / 600,
          (hostElement.clientHeight - 16) / Math.max(1, paperElement.offsetHeight),
        ),
      )
    })
    observer.observe(hostElement)
    observer.observe(paperElement)
    return () => observer.disconnect()
  }, [])
  return (
    <div
      ref={host}
      className={`pointer-events-none relative overflow-hidden bg-surface ${compact ? 'h-24' : 'h-48'}`}
      aria-hidden="true"
    >
      <div
        ref={paper}
        className="absolute top-2 left-1/2 w-[600px] origin-top"
        style={{ transform: `translateX(-50%) scale(${scale})` }}
      >
        <PostingPoster posting={thumbnailPosting} design={design} logoUrl={logoUrl} />
      </div>
    </div>
  )
}
