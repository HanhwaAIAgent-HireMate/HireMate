import { ExternalLink } from 'lucide-react'

/**
 * 원본 PDF 열기. 블라인드 채용에서 원본에 지원자 이름이 있으면 옆에 안내만 한다. 화면은 이름을 가려 보여 주므로 원본을 열면
 * 이름이 보인다는 것을 미리 알린다. 원본에 남은 출신 학교 · 학점은 HR이 블라인드 위반을 확인하려고 여는 것이라 묻지 않는다
 */
export function OriginalPdfLink({
  href,
  showsName = false,
}: {
  href: string
  showsName?: boolean
}) {
  return (
    <span className="inline-flex items-center">
      {showsName && <span className="mr-2">원본에는 이름이 보여요</span>}
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        <ExternalLink className="size-3" />
        원본 PDF
      </a>
    </span>
  )
}
