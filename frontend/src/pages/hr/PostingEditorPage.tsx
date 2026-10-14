import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Skeleton } from '@/components/ui/skeleton'
import type { AiMessage } from '@/features/posting/AiRequestPanel'
import { useCreateRecruitment, usePosting } from '@/features/posting/api'
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
  const [messages, setMessages] = useState<AiMessage[]>([])
  if (posting.isError) return <EditorSkeleton title="공고 편집" message="공고를 찾지 못했어요." />
  if (!posting.data) return <EditorSkeleton title="공고 편집" />
  // 서버의 본문이 바뀌면(적용 · 되돌리기 · 저장) 편집 상태를 새로 연다
  return (
    <PostingEditor
      key={JSON.stringify(posting.data.content)}
      posting={posting.data}
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
