import type { Schemas } from '@/lib/api/client'
import './posting-roles.css'

export type PostingRole = Schemas['PostingRole']

export function PostingRolesTable({ roles }: { roles: PostingRole[] }) {
  const lines = (items: string[]) => (
    <ul>
      {items.map((text, index) => (
        <li key={index}>{text}</li>
      ))}
    </ul>
  )
  return (
    <div className="posting-roles">
      <table aria-label="직무별 모집 내용">
        <thead>
          <tr>
            <th scope="col">직무</th>
            <th scope="col">구분</th>
            <th scope="col">주요 업무</th>
            <th scope="col">자격 요건</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((role, index) => (
            <tr key={`${role.name}-${index}`}>
              <th scope="row" data-label="직무">
                {role.name}
              </th>
              <td data-label="구분">{role.career || '미정'}</td>
              <td data-label="주요 업무">{lines(role.duties)}</td>
              <td data-label="자격 요건">
                {role.qualifications.length > 0 && (
                  <>
                    <strong>필수 사항</strong>
                    {lines(role.qualifications)}
                  </>
                )}
                {role.preferred.length > 0 && (
                  <>
                    <strong>우대 사항</strong>
                    {lines(role.preferred)}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
