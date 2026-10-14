import { useParams } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { usePublicPosting } from '@/features/posting/api'
import { CareersHeader, CareersPosting } from '@/features/posting/CareersPosting'

// APL-01 자체 채용 페이지. 지원자는 여기서 공고를 보고 지원한다
export function PostingPage() {
  const { postingId = '' } = useParams()
  const posting = usePublicPosting(postingId)

  if (posting.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-center">
        <div>
          <h1 className="text-lg font-semibold">채용 공고</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            공고를 찾지 못했어요. 주소를 다시 확인해 주세요.
          </p>
        </div>
      </div>
    )
  }
  if (!posting.data) {
    return (
      <div className="p-6">
        <h1 className="sr-only">채용 공고</h1>
        <Skeleton className="h-80 w-full" />
      </div>
    )
  }
  return (
    <div className="min-h-screen">
      <CareersHeader companyName={posting.data.companyName} />
      <main className="mx-auto max-w-[1040px] px-6 py-8">
        <CareersPosting posting={posting.data} applyPath={`/careers/${postingId}/apply`} />
      </main>
    </div>
  )
}
