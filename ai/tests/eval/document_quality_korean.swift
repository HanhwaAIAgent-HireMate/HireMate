// Generate the synthetic Korean fixture on macOS with the system font.
// The generated PDF is committed, so CI does not need Swift or the font.
import Foundation
import CoreGraphics
import CoreText

let destination = CommandLine.arguments.count == 2
    ? CommandLine.arguments[1]
    : "tests/samples/document_quality_korean.pdf"
let output = URL(fileURLWithPath: destination) as CFURL
var mediaBox = CGRect(x: 0, y: 0, width: 612, height: 792)
guard let context = CGContext(output, mediaBox: &mediaBox, nil) else {
    fatalError("Cannot create PDF")
}

func draw(_ text: String, x: CGFloat, y: CGFloat, size: CGFloat) {
    let font = CTFontCreateWithName("AppleSDGothicNeo-Regular" as CFString, size, nil)
    guard CTFontCopyPostScriptName(font) as String == "AppleSDGothicNeo-Regular" else {
        fatalError("AppleSDGothicNeo-Regular is required to regenerate the Korean fixture")
    }
    let attributes: [NSAttributedString.Key: Any] = [
        NSAttributedString.Key(kCTFontAttributeName as String): font
    ]
    let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: attributes))
    context.textMatrix = .identity
    context.textPosition = CGPoint(x: x, y: y)
    CTLineDraw(line, context)
}

context.beginPDFPage(nil)
draw("자  기  소  개  서", x: 70, y: 748, size: 18)
draw("지원동기", x: 70, y: 710, size: 14)
draw("예약 변경 정책을", x: 70, y: 685, size: 11)
draw("데이터로 확인했습니다.", x: 70, y: 668, size: 11)
draw("지원서 1", x: 70, y: 55, size: 9)
context.endPDFPage()
context.closePDF()
