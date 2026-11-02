import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { NoteEditor } from './NoteEditor'
import { useWorkspace } from './sessions'
import { api, unwrap } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'

/** 개인 메모는 이 API로 보내지 않는다. 공유 기록은 작성한 계정만 수정한다. */
export function SharedNotes({
  stageId,
  applicationId,
  interviewer = false,
  editable = false,
  initiallyOpen = interviewer,
}: {
  stageId: string
  applicationId: string
  interviewer?: boolean
  editable?: boolean
  initiallyOpen?: boolean
}) {
  const [open, setOpen] = useState(initiallyOpen)
  const client = useQueryClient()
  const workspace = useWorkspace(stageId, applicationId, interviewer)
  const query = useQuery({
    queryKey: ['interview', 'shared-notes', stageId, applicationId, interviewer],
    enabled: open,
    queryFn: () =>
      interviewer
        ? unwrap(
            api.GET('/api/interviewer/sessions/{stageId}/{applicationId}/shared-notes', {
              params: { path: { stageId, applicationId } },
            }),
          )
        : unwrap(
            api.GET('/api/stages/{stageId}/candidates/{applicationId}/interview/shared-notes', {
              params: { path: { stageId, applicationId } },
            }),
          ),
  })
  const mine = query.data?.find((note) => note.mine)
  return (
    <section className="space-y-3">
      <Button variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>
        인사 / 실무 공유 기록 {open ? '닫기' : '보기'}
      </Button>
      {open && (
        <>
          <p className="text-xs text-muted-foreground">
            채용 담당자와 배정된 면접관에게 공개돼요. 내 개인 메모는 포함되지 않아요.
          </p>
          {query.isError ? (
            <Button variant="outline" onClick={() => void query.refetch()}>
              공유 기록 다시 불러오기
            </Button>
          ) : query.isPending ? (
            <p>공유 기록을 불러오는 중이에요.</p>
          ) : (
            <>
              {(['HR', 'PRACTICAL'] as const).map((role) => (
                <div key={role} className="space-y-2 rounded-xl border p-3">
                  <h4 className="text-sm font-semibold">
                    {role === 'HR' ? '인사' : '실무'} 공유 기록
                  </h4>
                  {query.data
                    ?.filter((note) => note.role === role && !note.mine)
                    .map((note) => (
                      <article key={note.memberId} className="text-sm">
                        <p className="text-xs text-muted-foreground">
                          {note.name} · {formatDateTime(note.updatedAt)}
                        </p>
                        <p className="whitespace-pre-wrap">{note.text || '기록 없음'}</p>
                      </article>
                    ))}
                  {interviewer && workspace.data?.myRole === role && (
                    <NoteEditor
                      stageId={stageId}
                      applicationId={applicationId}
                      field="shared-note"
                      label="내 공유 기록"
                      description="공유할 면접 사실과 확인한 내용을 적어 주세요. 다른 담당자의 기록은 수정할 수 없어요."
                      text={mine?.text ?? ''}
                      version={mine?.version ?? 0}
                      editable={editable}
                      reload={() => query.refetch({ throwOnError: true })}
                      save={async (text, expectedVersion) => {
                        const stored = await unwrap(
                          api.PUT(
                            '/api/interviewer/sessions/{stageId}/{applicationId}/shared-notes/me',
                            {
                              params: { path: { stageId, applicationId } },
                              body: { text, expectedVersion },
                            },
                          ),
                        )
                        await client.invalidateQueries({
                          queryKey: ['interview', 'shared-notes', stageId, applicationId],
                        })
                        return stored
                      }}
                    />
                  )}
                  {!query.data?.some((note) => note.role === role) &&
                    !(interviewer && workspace.data?.myRole === role) && (
                      <p className="text-sm text-muted-foreground">아직 공유 기록이 없어요.</p>
                    )}
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  )
}
