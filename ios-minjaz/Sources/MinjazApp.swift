import SwiftUI

@main
struct MinjazApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.layoutDirection, .rightToLeft)
                .preferredColorScheme(.light)
        }
    }
}

enum MobileTab: String, CaseIterable, Identifiable {
    case discover, workspace, orders, services, account
    var id: String { rawValue }
    var title: String {
        switch self {
        case .discover: return "استكشف"
        case .workspace: return "المشاريع"
        case .orders: return "طلباتي"
        case .services: return "الخدمات"
        case .account: return "حسابي"
        }
    }
    var symbol: String {
        switch self {
        case .discover: return "square.grid.2x2"
        case .workspace: return "briefcase"
        case .orders: return "tray.full"
        case .services: return "sparkles.rectangle.stack"
        case .account: return "person.crop.circle"
        }
    }
    var path: String {
        switch self {
        case .discover: return "/"
        case .workspace: return "/workspace#tasks-section"
        case .orders: return "/workspace#orders-section"
        case .services: return "/digital-services"
        case .account: return "/workspace#profile"
        }
    }
}

struct ContentView: View {
    @StateObject private var browser = MinjazBrowser()
    @StateObject private var catalog = MinjazCatalog()
    @State private var selected: MobileTab = .discover
    @State private var sharing = false

    private let blue = Color(red: 0.29, green: 0.32, blue: 0.84)
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 23, weight: .bold))
                    .foregroundStyle(blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text("مِنجاز").font(.system(size: 20, weight: .heavy))
                    Text(selected == .discover ? "اكتشف تخصصات المستقلين" : selected.title)
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if selected != .discover {
                    Button { browser.reload() } label: {
                        Image(systemName: "arrow.clockwise").frame(width: 37, height: 37)
                    }
                    .accessibilityLabel("تحديث الصفحة")
                }
                Button { sharing = true } label: {
                    Image(systemName: "square.and.arrow.up").frame(width: 37, height: 37)
                }
                .accessibilityLabel("مشاركة مِنجاز")
            }
            .padding(.horizontal, 16).padding(.vertical, 9)
            .background(.white)

            Group {
                if selected == .discover {
                    CatalogView(catalog: catalog) { service in
                        // Preserve the category and specialty selected natively.
                        // The web workspace checks these IDs against its live API,
                        // and the server still validates every actual submission.
                        guard service.id > 0, service.category_id > 0 else { return }
                        browser.open(path: "/workspace?category_id=\(service.category_id)&service_id=\(service.id)#tasks-section")
                        selected = .workspace
                    }
                } else {
                    ZStack {
                        MinjazWebView(browser: browser)
                        if browser.isLoading {
                            VStack(spacing: 12) {
                                ProgressView()
                                Text("جاري فتح مِنجاز…").font(.subheadline)
                            }
                            .padding(20)
                            .background(.white.opacity(0.96), in: RoundedRectangle(cornerRadius: 16))
                        }
                        if let error = browser.error {
                            VStack(spacing: 16) {
                                Image(systemName: "wifi.exclamationmark").font(.largeTitle)
                                Text(error).multilineTextAlignment(.center)
                                Button("إعادة المحاولة") { browser.reload() }
                                    .buttonStyle(.borderedProminent)
                            }
                            .padding(30)
                            .background(.white, in: RoundedRectangle(cornerRadius: 18))
                            .padding(20)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            HStack(spacing: 0) {
                ForEach(MobileTab.allCases) { tab in
                    Button {
                        if selected != tab {
                            selected = tab
                            if tab != .discover { browser.open(path: tab.path) }
                        }
                    } label: {
                        VStack(spacing: 5) {
                            Image(systemName: tab.symbol)
                                .font(.system(size: 19, weight: .semibold))
                            Text(tab.title).font(.system(size: 10, weight: .semibold))
                        }
                        .foregroundStyle(selected == tab ? blue : Color.secondary)
                        .frame(maxWidth: .infinity).frame(height: 54)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(selected == tab ? .isSelected : [])
                }
            }
            .padding(.horizontal, 8).padding(.top, 5).padding(.bottom, 2)
            .background(.white)
        }
        .background(Color(red: 0.97, green: 0.97, blue: 0.98))
        .sheet(isPresented: $sharing) {
            MinjazShareSheet(items: [browser.webView.url ?? browser.origin])
        }
        .sheet(item: $browser.shareFile) { item in
            MinjazShareSheet(items: [item.url])
        }
        .task { await catalog.load(origin: browser.origin) }
    }
}

struct MinjazShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
