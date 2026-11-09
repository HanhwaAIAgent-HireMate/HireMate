import { useState } from 'react'

import { ApplicantIcon } from '@/components/ApplicantIcon'
import { applicantPhoto } from '@/lib/applicant-photo'

/**
 * 지원자 이름 옆의 원형 사진 (선택 지원자 상세). 예시 사진이 없거나(블라인드 · 성별을 모르는 이름)
 * 불러오지 못하면 목록과 같은 지원자 아이콘을 보인다.
 */
export function ApplicantAvatar({ applicationId, name }: { applicationId: string; name: string }) {
  const src = applicantPhoto(applicationId, name)
  const [failed, setFailed] = useState(false)
  if (!src || failed) return <ApplicantIcon />
  return (
    <img
      src={src}
      alt=""
      aria-hidden
      onError={() => setFailed(true)}
      className="size-20 shrink-0 rounded-full border object-cover object-top"
    />
  )
}
