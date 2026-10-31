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

struct MinjazBrandMark: View {
    var dimension: CGFloat = 34

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { layer in
                RoundedRectangle(cornerRadius: dimension * 0.10, style: .continuous)
                    .fill(layer == 0 ? MinjazUI.deep : MinjazUI.primary)
                    .frame(width: dimension * 0.74, height: dimension * 0.48)
                    .rotationEffect(.degrees(-35))
                    .offset(y: CGFloat(layer - 1) * dimension * 0.16)
            }
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
