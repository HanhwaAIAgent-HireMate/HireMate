import { BarChart, LineChart, PieChart, RadarChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { init, use as register, type EChartsCoreOption } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useLayoutEffect, useRef } from 'react'

// 리포트가 쓰는 차트만 불러 번들을 줄인다. SVG로 그려 화면과 PDF가 같은 그림을 쓴다
register([
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  SVGRenderer,
])

/** 움직임을 끈 옵션. 카드 폭별 옵션(baseOption · media)이면 기본 옵션에 끈다 */
function withoutAnimation(option: EChartsCoreOption): EChartsCoreOption {
  if ('baseOption' in option)
    return { ...option, baseOption: { ...(option.baseOption as object), animation: false } }
  return { ...option, animation: false }
}

/** ECharts 한 장. 부모 폭이 바뀌면 다시 맞춘다 */
export function EChart({
  option,
  height,
  label,
  still = false,
}: {
  option: EChartsCoreOption
  height: number
  label: string
  /** 인쇄용. 움직임 없이 바로 다 그린다 */
  still?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)

  // 인쇄 직전에 바뀐 그림(지원자번호만)이 인쇄본에 들어가도록 화면에 그리기 전에 바로 그린다
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const chart = init(element, null, { renderer: 'svg' })
    chart.setOption(still ? withoutAnimation(option) : option)
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element)
    return () => {
      observer.disconnect()
      chart.dispose()
    }
  }, [option, still])

  return <div ref={ref} role="img" aria-label={label} style={{ height }} className="w-full" />
}
