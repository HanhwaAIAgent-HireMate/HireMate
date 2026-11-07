import { useEffect, useMemo, useState } from 'react'
import type { PosterPosting } from '@/features/posting/PostingPoster'
import type { PosterDesign } from '@/features/posting/poster-design'
import type { PosterChanges } from './poster-preview'
import { layoutNativePoster } from './poster-layout'
import { inlinePosterSvg, loadPosterFonts, POSTER_FONT } from './poster-svg'
import { PosterMotion } from './PosterMotion'
import { PosterVideo } from './PosterVideo'
import {
  posterBindings,
  posterCanvasObjects,
  readPosterCanvas,
  upgradeCanvaPoster,
  layoutCanvaPoster,
  preparePosterLogo,
  posterLogoSurface,
  recolorGeneratedPoster,
} from '@/features/posting/poster-canvas'

/** SVG로 출력해 웹 미리보기와 PDF 복제 모두에서 벡터 글자를 유지한다. */
export function CanvasPoster({
  posting,
  design,
  logoUrl,
  sectionIds = false,
  changes,
  compact = false,
}: {
  posting: PosterPosting
  design: PosterDesign
  logoUrl?: string
  sectionIds?: boolean
  changes?: PosterChanges
  compact?: boolean
}) {
  const [rendered, setRendered] = useState<{
    key: string
    svg: string
    headerHeight: number
    headerInk: string
    media?: {
      url: string
      ratio: number
      overlay: string
      preserveAspectRatio: boolean
      frame?: { left: number; top: number; width: number; height: number }
    }
    boxes: { id: string; left: number; top: number; width: number; height: number }[]
  } | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const values = useMemo(() => posterBindings(posting, design), [posting, design])
  const key = JSON.stringify([
    design.canvasJson,
    design.color,
    values,
    logoUrl,
    design.showLogo,
    design.stageIcons,
    changes,
  ])
  useEffect(() => {
    if (!design.canvasJson) return
    let disposed = false
    let canvas: { dispose: () => Promise<boolean> } | undefined
    void (async () => {
      try {
        await loadPosterFonts(Object.values(values).join('\n'))
        const doc = recolorGeneratedPoster(
          readPosterCanvas(await upgradeCanvaPoster(design.canvasJson!, posting, design.color)),
          design.color,
        )
        const F = await import('fabric')
        F.cache.clearFontCache(POSTER_FONT)
        await document.fonts.ready
        if (disposed) return
        const target = new F.StaticCanvas(document.createElement('canvas'), {
          width: doc.width,
          height: doc.height,
          backgroundColor: '#ffffff',
        })
        canvas = target
        if (
          !doc.originalRender &&
          design.tagline &&
          !doc.objects.some((object) => object.binding === 'tagline')
        ) {
          const title = doc.objects.find((object) => object.binding === 'title')
          doc.objects.push({
            type: 'Textbox',
            hmId: 'tagline',
            binding: 'tagline',
            text: '',
            left: Number(title?.left ?? 40),
            top: Number(title?.top ?? 96) + Number(title?.height ?? 60) + 16,
            width: Number(title?.width ?? 480),
            fontSize: 14,
            fill: title?.fill ?? '#24313e',
            originX: 'left',
            originY: 'top',
            fontFamily: POSTER_FONT,
          })
        }
        const objects = posterCanvasObjects(doc, values, design.color)
        await target.loadFromJSON({ objects })
        if (doc.nativeLayout) {
          await layoutNativePoster(target, doc, posting, design)
        } else if (doc.canvaLayout) {
          await layoutCanvaPoster(target, doc, posting, design)
        } else {
          // 공고 문구가 길어지거나 글꼴 크기를 키우면 다음 행을 내려서 내용을 보존한다.
          const rows = new Map<
            number,
            { object: ReturnType<typeof target.getObjects>[number]; oldHeight: number }[]
          >()
          target.getObjects().forEach((object, index) => {
            const source = doc.objects[index]
            if (typeof source?.binding !== 'string') return
            const alignedTop =
              [...rows.keys()].find((top) => Math.abs(top - object.top) < 8) ?? object.top
            const row = rows.get(alignedTop) ?? []
            row.push({
              object,
              oldHeight:
                typeof source.hmSourceHeight === 'number'
                  ? source.hmSourceHeight
                  : typeof source.height === 'number'
                    ? source.height
                    : object.height,
            })
            rows.set(alignedTop, row)
          })
          let offset = 0
          let bottom = 0
          const bands = [{ old: 0, next: 0 }]
          const background = target
            .getObjects()
            .find((_, index) => doc.objects[index]?.hmId === 'canva-background')
          const backgroundHeight = background?.getScaledHeight() ?? 0
          let backgroundBottom = backgroundHeight
          for (const [top, row] of [...rows].sort(([a], [b]) => a - b)) {
            const nextTop = Math.max(top + offset, bottom ? bottom + 16 : top)
            row.forEach(({ object }) => {
              object.set({ top: nextTop })
              object.setCoords()
            })
            const height = Math.max(...row.map(({ object }) => object.getScaledHeight()))
            offset =
              nextTop -
              top +
              Math.max(0, height - Math.max(...row.map(({ oldHeight }) => oldHeight)))
            bottom = nextTop + height
            if (top > 0 && top < backgroundHeight) {
              bands.push({ old: top, next: nextTop })
              const end = top + Math.max(...row.map(({ oldHeight }) => oldHeight))
              const nextRow = [...rows.keys()]
                .filter((value) => value > top)
                .sort((a, b) => a - b)[0]
              if (end < Math.min(backgroundHeight, nextRow ?? backgroundHeight))
                bands.push({ old: end, next: nextTop + height })
              backgroundBottom = backgroundHeight + offset
            }
          }
          const height = Math.max(doc.height, bottom + 40)
          if (height > 20000) throw new Error('포스터 내용이 너무 길어요.')
          if (background instanceof F.FabricImage) {
            // 글이 길어질 때 원본의 행 구분선과 배경도 해당 행 아래로 이어 붙인다.
            bands.push({ old: backgroundHeight, next: backgroundBottom })
            target.remove(background)
            for (let index = 1; index < bands.length; index++) {
              const start = bands[index - 1]
              const end = bands[index]
              const cropHeight = ((end.old - start.old) / backgroundHeight) * background.height
              if (cropHeight <= 0) continue
              const strip = new F.FabricImage(background.getElement(), {
                left: 0,
                top: start.next,
                originX: 'left',
                originY: 'top',
                cropY: (start.old / backgroundHeight) * background.height,
                width: background.width,
                height: cropHeight,
                scaleX: doc.width / background.width,
                scaleY: (end.next - start.next) / cropHeight,
              })
              target.add(strip)
              target.sendObjectToBack(strip)
            }
            if (height > backgroundBottom) {
              const continuation = doc.continuation
              const sampleTop = continuation?.sampleTop ?? backgroundHeight * 0.6
              const sampleBottom = continuation?.sampleBottom ?? backgroundHeight * 0.8
              const sampleHeight = sampleBottom - sampleTop
              // 원본 본문의 종이색·구분선·열 장식을 반복해 새 항목도 같은 테마로 잇는다.
              for (let top = backgroundBottom; top < height; top += sampleHeight) {
                const stripHeight = Math.min(sampleHeight, height - top)
                const strip = new F.FabricImage(background.getElement(), {
                  left: 0,
                  top,
                  originX: 'left',
                  originY: 'top',
                  cropY: (sampleTop / backgroundHeight) * background.height,
                  width: background.width,
                  height: (stripHeight / backgroundHeight) * background.height,
                  scaleX: doc.width / background.width,
                  scaleY: backgroundHeight / background.height,
                })
                target.add(strip)
                target.sendObjectToBack(strip)
              }
            }
          }
          if (height > doc.height) {
            target.setDimensions({ height })
            target.getObjects().forEach((object, index) => {
              if (!background && !doc.objects[index]?.binding)
                object.set({
                  top: (object.top * height) / doc.height,
                  scaleY: (object.scaleY * height) / doc.height,
                })
            })
          }
        }
        const coverEnd = target
          .getObjects()
          .find((object) => object.get('hmId') === 'orshot-cover-end')
        if (logoUrl && design.showLogo && design.logoFileId) {
          const loaded = await F.FabricImage.fromURL(logoUrl)
          loaded.scale(Math.min(1, 1600 / Math.max(loaded.width, loaded.height)))
          const background = doc.canvaLayout ? target.backgroundColor : design.color
          const headerColor = doc.canvaLayout
            ? objects.find((object) => object.binding === 'title')?.fill === '#ffffff'
              ? '#082858'
              : '#ffffff'
            : background
          const prepared = preparePosterLogo(
            loaded.toCanvasElement(),
            typeof headerColor === 'string' ? headerColor : '#ffffff',
          )
          const logo = await F.FabricImage.fromURL(prepared.toDataURL('image/png'))
          logo.scaleToWidth(
            Math.min(prepared.width / Math.max(1, prepared.height) > 2.2 ? 132 : 64, logo.width),
          )
          if (coverEnd && logo.getScaledHeight() > 60) logo.scaleToHeight(60)
          logo.set({
            left: coverEnd ? 40 : doc.width - logo.getScaledWidth() - 40,
            top: 20,
            originX: 'left',
            originY: 'top',
          })
          target.add(
            new F.Rect({
              left: logo.left - 4,
              top: logo.top - 3,
              width: logo.getScaledWidth() + 8,
              height: logo.getScaledHeight() + 6,
              rx: 5,
              ry: 5,
              fill: posterLogoSurface(typeof headerColor === 'string' ? headerColor : '#ffffff'),
              strokeWidth: 0,
              originX: 'left',
              originY: 'top',
            }),
          )
          target.add(logo)
        }
        if (!disposed) {
          const headerBindings = ['company', 'title', 'tags', 'tagline']
          const headerHeight =
            (Math.min(
              target.height,
              coverEnd?.top ??
                Math.max(
                  doc.nativeLayout?.headerBottom ?? doc.canvaLayout?.headerHeight ?? 0,
                  ...target
                    .getObjects()
                    .filter((object) => headerBindings.includes(String(object.get('hmId'))))
                    .map((object) => object.top + object.getScaledHeight() + 32),
                ),
            ) /
              target.height) *
            100
          const ids = [
            ...(changes?.stages.map((name) => `stage:${name}`) ?? []),
            ...(changes?.bindings ?? []),
          ]
          const boxes = ids.flatMap((id) => {
            if (id === 'header-motion')
              return [{ id, left: 0, top: 0, width: 100, height: headerHeight }]
            const bounds = target
              .getObjects()
              .filter((object) => object.get('hmId') === id)
              .map((object) => object.getBoundingRect())
            if (!bounds.length) return []
            const left = Math.min(...bounds.map((b) => b.left)),
              top = Math.min(...bounds.map((b) => b.top))
            return [
              {
                id,
                left: (left / target.width) * 100,
                top: (top / target.height) * 100,
                width:
                  ((Math.max(...bounds.map((b) => b.left + b.width)) - left) / target.width) * 100,
                height:
                  ((Math.max(...bounds.map((b) => b.top + b.height)) - top) / target.height) * 100,
              },
            ]
          })
          const headerInk = target
            .getObjects()
            .find((object) => object.get('hmId') === 'title')?.fill
          const svg = inlinePosterSvg(target.toSVG())
          let media
          if (doc.media) {
            target.backgroundColor = 'transparent'
            const cover = target
              .getObjects()
              .find((object) => object.get('hmId') === 'canva-header')
            cover?.set({ excludeFromExport: true })
            media = {
              url: doc.media.url,
              ratio: doc.media.height / doc.media.clipHeight,
              preserveAspectRatio: doc.originalRender === true,
              overlay: inlinePosterSvg(target.toSVG()),
              frame:
                coverEnd && cover
                  ? {
                      left: (cover.left / doc.width) * 100,
                      top: (cover.top / coverEnd.top) * 100,
                      width: (cover.getScaledWidth() / doc.width) * 100,
                      height: (cover.getScaledHeight() / coverEnd.top) * 100,
                    }
                  : undefined,
            }
          }
          setRendered({
            key,
            svg,
            media,
            headerHeight,
            headerInk: typeof headerInk === 'string' ? headerInk : '#24313e',
            boxes,
          })
          setFailed(null)
        }
      } catch {
        if (!disposed) setFailed(key)
      }
    })()
    return () => {
      disposed = true
      void canvas?.dispose()
    }
    // key contains the complete drawing inputs; reloading prevents stale canvas requests from winning.
  }, [key, design, logoUrl, values, posting, changes])
  return (
    <article
      className="posting-poster relative bg-white"
      aria-label={`${posting.companyName} ${posting.content.title} 채용 포스터`}
      data-poster-highlight={changes?.all || undefined}
    >
      {rendered?.key === key && (
        <div
          role="img"
          aria-label={`${posting.companyName} ${posting.content.title} 채용 포스터`}
          className="poster-vector w-full"
          dangerouslySetInnerHTML={{ __html: rendered.svg }}
        />
      )}
      {rendered?.key === key &&
        !compact &&
        rendered.media &&
        (rendered.media.preserveAspectRatio || design.motion !== 'NONE') && (
          <PosterVideo
            key={rendered.media.url}
            url={rendered.media.url}
            ratio={rendered.media.ratio}
            preserveAspectRatio={rendered.media.preserveAspectRatio}
            headerHeight={rendered.headerHeight}
            overlay={rendered.media.overlay}
            frame={rendered.media.frame}
          />
        )}
      {rendered?.key === key && !compact && !rendered.media && (
        <div
          className="poster-motion-region absolute inset-x-0 top-0"
          style={{ height: `${rendered.headerHeight}%`, color: rendered.headerInk }}
        >
          <PosterMotion effect={design.motion} />
        </div>
      )}
      {rendered?.key === key &&
        rendered.boxes.map((box) => (
          <div
            key={box.id}
            data-poster-highlight
            aria-label={`${box.id.replace('stage:', '')} 수정안`}
            className="poster-change-overlay pointer-events-none absolute"
            style={{
              left: `${box.left}%`,
              top: `${box.top}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
            }}
          />
        ))}
      <div className={rendered?.key === key ? 'sr-only' : 'space-y-5 p-8'}>
        {failed === key && (
          <p role="alert">
            외부 디자인을 표시하지 못해 공고 내용을 보여드려요. 기본 템플릿을 선택하거나 다시 가져와
            주세요.
          </p>
        )}
        {Object.entries(values)
          .filter(([, value]) => value)
          .map(([binding, value]) => (
            <section
              key={binding}
              id={
                sectionIds
                  ? binding === 'intro'
                    ? 'company'
                    : binding === 'benefits'
                      ? 'benefits'
                      : undefined
                  : undefined
              }
            >
              <p className="text-sm whitespace-pre-wrap">{value}</p>
            </section>
          ))}
      </div>
    </article>
  )
}
