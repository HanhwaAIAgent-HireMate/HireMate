import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { Skeleton } from '@/components/ui/skeleton'
import type { AiMessage } from '@/features/posting/AiRequestPanel'
import { useCreateRecruitment, usePosting } from '@/features/posting/api'
import type { CareerLevel } from '@/features/posting/conditions'
import type { LineFocus } from '@/features/posting/focus'
import { PostingEditor } from '@/features/posting/PostingEditor'
import { PostingFormatDialog, type PostingFormat } from '@/features/posting/PostingFormatDialog'
import { useSavePoster } from '@/features/posting/poster-api'
import type { PosterDesign } from '@/features/posting/poster-design'
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
  const navigate = useNavigate()
  const savePoster = useSavePoster(recruitmentId)
  const [choosingFormat, setChoosingFormat] = useState(false)
  const posting = usePosting(recruitmentId)
  const [messages, setMessages] = useState<AiMessage[]>([])
  const [focus, setFocus] = useState<LineFocus | null>(null)
  const [writtenFor, setWrittenFor] = useState<CareerLevel | null>(null)
  if (posting.isError) return <EditorSkeleton title="공고 편집" message="공고를 찾지 못했어요." />
  if (!posting.data) return <EditorSkeleton title="공고 편집" />
  const selectFormat = async (format: PostingFormat, design: PosterDesign) => {
    try {
      await savePoster.mutateAsync({ ...design, enabled: format === 'poster' })
      await navigate(
        `/hr/recruitments/${recruitmentId}/posting/${format === 'poster' ? 'poster' : 'publish'}`,
      )
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }
  // 서버의 본문이 바뀌면(적용 · 되돌리기 · 저장) 편집 상태를 새로 연다
  return (
    <>
      <PostingEditor
        key={JSON.stringify(posting.data.content)}
        posting={posting.data}
        messages={messages}
        setMessages={setMessages}
        focus={focus}
        setFocus={setFocus}
        writtenFor={writtenFor}
        setWrittenFor={setWrittenFor}
        onNext={() => setChoosingFormat(true)}
      />
      {choosingFormat && (
        <PostingFormatDialog
          posting={posting.data}
          pending={savePoster.isPending}
          onClose={() => setChoosingFormat(false)}
          onSelect={(format, design) => void selectFormat(format, design)}
        />
      )}
    </>
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
