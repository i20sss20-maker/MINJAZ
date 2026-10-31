import SwiftUI

/// One source of truth for app typography and surfaces. Uses the system's
/// Arabic text shaping and Dynamic Type instead of shipping a brittle font.
enum MinjazUI {
    static let primary = Color(red: 101/255, green: 88/255, blue: 245/255)
    static let deep = Color(red: 43/255, green: 30/255, blue: 104/255)
    static let ink = Color(red: 24/255, green: 25/255, blue: 49/255)
    static let muted = Color(red: 105/255, green: 111/255, blue: 132/255)
    static let canvas = Color(red: 248/255, green: 248/255, blue: 252/255)
    static let tinted = Color(red: 242/255, green: 239/255, blue: 255/255)
    static let border = Color(red: 232/255, green: 231/255, blue: 241/255)

    static func heading(_ size: CGFloat = 25) -> Font {
        .system(size: size, weight: .bold, design: .default)
    }
    static func body(_ size: CGFloat = 15, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }
}

/// The three parallelograms and checkmark are the same geometry as
/// public/icon.svg and the Android launcher icon, not a generic stacked icon.
struct MinjazBrandMark: View {
    var dimension: CGFloat = 34

    var body: some View {
        Canvas { context, size in
            func polygon(_ points: [(CGFloat, CGFloat)]) -> Path {
                var path = Path()
                for (index, pair) in points.enumerated() {
                    let point = CGPoint(x: pair.0 * size.width / 28,
                                        y: pair.1 * size.height / 28)
                    if index == 0 { path.move(to: point) }
                    else { path.addLine(to: point) }
                }
                path.closeSubpath()
                return path
            }
            context.fill(polygon([(5, 19), (15, 19), (17, 15), (7, 15)]),
                         with: .color(Color(red: 44/255, green: 201/255, blue: 183/255)))
            context.fill(polygon([(7, 14), (18, 14), (20, 10), (9, 10)]),
                         with: .color(Color(red: 138/255, green: 125/255, blue: 255/255)))
            context.fill(polygon([(9, 9), (21, 9), (19, 13), (7, 13)]),
                         with: .color(MinjazUI.primary))
            var tick = Path()
            tick.move(to: CGPoint(x: 19 * size.width / 28, y: 18 * size.height / 28))
            tick.addLine(to: CGPoint(x: 21 * size.width / 28, y: 20 * size.height / 28))
            tick.addLine(to: CGPoint(x: 25 * size.width / 28, y: 16 * size.height / 28))
            context.stroke(tick, with: .color(MinjazUI.deep),
                           style: StrokeStyle(lineWidth: size.width * 0.065,
                                              lineCap: .round, lineJoin: .round))
        }
        .frame(width: dimension, height: dimension)
        .accessibilityHidden(true)
    }
}

struct MinjazSurface<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .background(.white, in: RoundedRectangle(cornerRadius: 19, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 19, style: .continuous)
                    .stroke(MinjazUI.border.opacity(0.65), lineWidth: 0.65)
            )
            .shadow(color: MinjazUI.deep.opacity(0.035), radius: 12, y: 5)
    }
}
