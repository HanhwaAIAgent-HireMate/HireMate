import { useParams } from 'react-router'

export function CareersPage() {
  const { postingId } = useParams()

  return <h1 className="p-6 text-2xl font-bold">채용 공고 {postingId}</h1>
}
