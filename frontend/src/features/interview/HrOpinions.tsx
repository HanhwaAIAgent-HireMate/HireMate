import { OpinionLine } from '@/features/interview/OpinionCard'
import { useCandidateOpinions } from '@/features/interview/opinions'

/** HR 지원자 카드의 면접관 의견. 결정은 HR이 결정 바에서 하고, AI는 의견을 요약하거나 합격을 권하지 않는다 */
export function HrOpinions({ stageId, applicationId }: { stageId: string; applicationId: string }) {
  const opinions = useCandidateOpinions(stageId, applicationId)
  if (!opinions.data?.length) return null
  return (
    <section aria-label="면접관 의견" className="space-y-2">
      <h4 className="text-sm font-semibold">면접관 의견</h4>
      <div className="grid gap-2 md:grid-cols-2">
        {opinions.data.map((opinion) => (
          <OpinionLine key={opinion.memberId} opinion={opinion} />
        ))}
      </div>
    </section>
  )
}
