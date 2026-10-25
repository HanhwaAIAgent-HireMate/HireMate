import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Skeleton } from '@/components/ui/skeleton'
import type { AiMessage } from '@/features/posting/AiRequestPanel'
import { useCreateRecruitment, usePosting, useScreeningCriteria } from '@/features/posting/api'
import { PostingEditor } from '@/features/posting/PostingEditor'
import { errorMessage } from '@/lib/api/client'

// 새 채용은 기업 공고 Template으로 공고 초안을 만들고 편집 화면으로 간다
export function PostingEditorPage() {
  const { recruitmentId } = useParams()
  return recruitmentId ? <EditPosting recruitmentId={recruitmentId} /> : <NewPosting />
}

function NewPosting() {
  const navigate = useNavigate()
  const create = useCreateRecruitment()
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    create.mutate(undefined, {
      onSuccess: (posting) =>
        void navigate(`/hr/recruitments/${posting.recruitmentId}/posting`, { replace: true }),
      onError: (error) => {
        toast.error(errorMessage(error))
        void navigate('/hr', { replace: true })
      },
    })
  }, [create, navigate])

  return <EditorSkeleton title="공고 편집" />
}

function EditPosting({ recruitmentId }: { recruitmentId: string }) {
  const posting = usePosting(recruitmentId)
  const criteria = useScreeningCriteria(recruitmentId)
  const [messages, setMessages] = useState<AiMessage[]>([])
  if (posting.isError || criteria.isError) {
    return <EditorSkeleton title="공고 편집" message="공고를 찾지 못했어요." />
  }
  if (!posting.data || !criteria.data) return <EditorSkeleton title="공고 편집" />
  // 편집기는 저장 · 적용 · 되돌리기 결과로 스스로 입력 상태를 맞춘다.
  // 저장하는 동안 다시 열면 이어서 저장할 서류 평가 기준과 AI 초안 진행이 끊긴다
  return (
    <PostingEditor
      key={recruitmentId}
      posting={posting.data}
      screening={criteria.data}
      messages={messages}
      setMessages={setMessages}
    />
  )
}

function EditorSkeleton({ title, message }: { title: string; message?: string }) {
  return (
    <div className="space-y-4 p-6">
      <h1 className="sr-only">{title}</h1>
      {message ? (
        <p className="text-sm text-muted-foreground">{message}</p>
      ) : (
        <>
          <Skeleton className="h-7 w-40" />
          <Skeleton className="h-40 w-full max-w-3xl" />
        </>
      )}
    </div>
  )
}
