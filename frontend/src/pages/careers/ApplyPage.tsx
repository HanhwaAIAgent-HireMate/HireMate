import { CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApplicationForm } from '@/features/apply/ApplicationForm'
import { usePublicPosting } from '@/features/posting/api'
import { BlindNotice, CareersHeader } from '@/features/posting/CareersPosting'

export function ApplyPage() {
  const { postingId = '' } = useParams()
  const posting = usePublicPosting(postingId)
  const [submitted, setSubmitted] = useState<{ applicationNo: number; name: string } | null>(null)
  const postingPath = `/careers/${postingId}`

  if (!posting.data) {
    return (
      <div className="p-6">
        <h1 className="sr-only">지원서</h1>
        {posting.isError ? (
          <p className="text-sm text-muted-foreground">공고를 찾지 못했어요.</p>
        ) : (
          <Skeleton className="h-80 w-full" />
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <CareersHeader companyName={posting.data.companyName} postingPath={postingPath} />
      <main className="mx-auto max-w-[1040px] px-6 py-8">
        {submitted ? (
          <div className="mx-auto max-w-md space-y-3 py-16 text-center">
            <CheckCircle2 className="mx-auto size-10 text-pass-foreground" />
            <h1 className="text-xl font-bold">지원이 완료됐어요</h1>
            <p className="text-sm text-muted-foreground">
              {submitted.name}님, {posting.data.content.title}에 지원해 주셔서 감사합니다.
              지원번호는 {submitted.applicationNo}번이에요. 접수 확인과 전형 결과는 입력한 이메일로
              안내드려요.
            </p>
            <Button variant="outline" asChild>
              <Link to={postingPath}>공고로 돌아가기</Link>
            </Button>
          </div>
        ) : posting.data.state !== 'OPEN' ? (
          <div className="py-16 text-center">
            <h1 className="text-xl font-bold">지원서</h1>
            <p className="mt-2 text-sm text-muted-foreground">지금은 지원 접수 기간이 아니에요.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {posting.data.content.blind && <BlindNotice />}
            <ApplicationForm posting={posting.data} onSubmitted={setSubmitted} />
          </div>
        )}
      </main>
    </div>
  )
}
