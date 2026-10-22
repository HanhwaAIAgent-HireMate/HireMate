/** 메일 아래에 붙는 안내의 칸 하나. optional인 기타 안내는 여러 줄이고 메일에 이름 없이 ※로 붙는다 */
export type GuideField<K extends string> = {
  key: K
  label: string
  placeholder: string
  /** backend 칸 길이와 같다 */
  maxLength: number
  optional?: boolean
}

/** 비어 있는 칸. 기타 안내는 비어도 경고하지 않는다 */
export function emptyFields<K extends string>(fields: GuideField<K>[], values: Record<K, string>) {
  return fields.filter((field) => !field.optional && !values[field.key].trim())
}
