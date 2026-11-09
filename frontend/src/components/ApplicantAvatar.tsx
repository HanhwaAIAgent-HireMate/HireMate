import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { ApplicantIcon } from '@/components/ApplicantIcon'
import { api } from '@/lib/api/client'

export function ApplicantAvatar({
  applicationId,
  recruitmentId,
}: {
  applicationId: string
  recruitmentId: string
}) {
  return <StoredAvatar recruitmentId={recruitmentId} applicationId={applicationId} />
}

function StoredAvatar({
  recruitmentId,
  applicationId,
}: {
  recruitmentId: string
  applicationId: string
}) {
  const photo = useQuery({
    queryKey: ['applicant-photo', recruitmentId, applicationId],
    queryFn: async () => {
      const result = await api.GET(
        '/api/recruitments/{recruitmentId}/applications/{applicationId}/photo',
        {
          params: { path: { recruitmentId, applicationId } },
          parseAs: 'blob',
        },
      )
      if (!result.response.ok) return null
      return result.data
        ? { blob: result.data, example: result.response.headers.get('X-Example-Photo') === 'true' }
        : null
    },
    retry: false,
  })
  const image = useRef<HTMLImageElement>(null)
  const [failed, setFailed] = useState<Blob | null>(null)
  const blob = photo.data?.blob ?? null
  useEffect(() => {
    if (!blob || !image.current) return
    const url = URL.createObjectURL(blob)
    image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [blob])
  if (!blob || blob === failed) return <ApplicantIcon />
  return (
    <img
      ref={image}
      alt=""
      aria-hidden
      onError={() => setFailed(blob)}
      className="size-20 shrink-0 rounded-full border object-cover object-top"
    />
  )
}
