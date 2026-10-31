import SwiftUI
import WebKit

/// Never forward a session cookie through a redirect: only exact first-party
/// HTTPS read endpoints are eligible for native API access.
private final class MinjazNoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

private enum NativeReadError: Error {
    case loginRequired, responseInvalid
}

enum NativeSection: String {
    case projects, orders, conversations, notifications, account

    var title: String {
        switch self {
        case .projects: return "المشاريع والفرص"
        case .orders: return "طلباتي"
        case .conversations: return "المحادثات"
        case .notifications: return "الإشعارات"
        case .account: return "حسابي"
        }
    }

    var endpoint: String? {
        switch self {
        case .projects: return "/api/v1/tasks"
        case .orders: return "/api/v1/orders"
        case .conversations: return "/api/v1/conversations"
        case .notifications: return "/api/v1/notifications"
        case .account: return nil
        }
    }

    var icon: String {
        switch self {
        case .projects: return "briefcase"
        case .orders: return "tray.full"
        case .conversations: return "bubble.left.and.bubble.right"
        case .notifications: return "bell"
        case .account: return "person.crop.circle"
        }
    }
}

struct NativeRecord: Identifiable {
    let id: Int
    let title: String
    let detail: String
    let status: String
    let timestamp: String
    let amount: String?
    let pending: Bool
}

struct NativeAccount {
    let name: String
    let email: String
    let role: String
    let verified: Bool
}

@MainActor
final class MinjazNativeWorkspace: ObservableObject {
    @Published private(set) var account: NativeAccount?
    @Published private(set) var records: [NativeRecord] = []
    @Published private(set) var isLoading = false
    @Published private(set) var loginRequired = false
    @Published private(set) var error: String?
    @Published private(set) var unread = 0

    private let origin: URL
    private let cookieStore: WKHTTPCookieStore
    private var generation = 0

    init() {
        let raw = (Bundle.main.object(forInfoDictionaryKey: "MinjazBaseURL") as? String) ?? ""
        guard let url = URL(string: raw), url.scheme == "https",
              url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil,
              (url.path.isEmpty || url.path == "/"),
              let host = url.host,
              url.port == nil || url.port == 443 else {
            preconditionFailure("MINJAZ first-party native API origin is missing")
        }
        #if MINJAZ_PREVIEW_BUILD
        precondition(host == "beta.minjazapp.com")
        #else
        precondition(host == "minjaz-app-prod-production.up.railway.app")
        #endif
        origin = url
        // This is the SAME cookie store as the embedded authenticated
        // workflow. No hidden second login or bearer-token transport.
        cookieStore = WKWebsiteDataStore.default().httpCookieStore
    }

    func load(_ section: NativeSection) async {
        generation += 1
        let current = generation
        isLoading = true
        error = nil
        loginRequired = false
        account = nil
        records = []

        do {
            let who = try await get("/api/v1/me")
            guard current == generation else { return }
            guard let user = who["user"] as? [String: Any] else {
                throw NativeReadError.responseInvalid
            }
            account = NativeAccount(
                name: string(user["name"]).isEmpty ? "مستخدم مِنجاز" : string(user["name"]),
                email: string(user["email"]),
                role: string(user["role"]),
                verified: (user["email_verified"] as? Bool) == true
            )
            if let endpoint = section.endpoint {
                let response = try await get(endpoint)
                guard current == generation else { return }
                guard let rows = response["items"] as? [[String: Any]] else {
                    throw NativeReadError.responseInvalid
                }
                records = Array(rows.prefix(200).compactMap { makeRecord($0, section: section) })
                if section == .notifications {
                    unread = (response["unread"] as? NSNumber)?.intValue ?? 0
                }
            }
        } catch NativeReadError.loginRequired {
            if current == generation { loginRequired = true }
        } catch {
            if current == generation {
                self.error = "تعذر تحميل البيانات من مِنجاز. تحقق من الاتصال ثم أعد المحاولة."
            }
        }
        if current == generation { isLoading = false }
    }

    private func get(_ path: String) async throws -> [String: Any] {
        guard path.hasPrefix("/api/v1/"),
              let url = URL(string: path, relativeTo: origin)?.absoluteURL,
              url.scheme == "https", url.host?.lowercased() == origin.host?.lowercased(),
              url.port == nil || url.port == 443 else {
            throw NativeReadError.responseInvalid
        }

        // WKWebView owns the real verified-email login. Native views share
        // only its first-party HttpOnly session, never JavaScript tokens.
        let allCookies: [HTTPCookie] = await withCheckedContinuation { continuation in
            cookieStore.getAllCookies { continuation.resume(returning: $0) }
        }
        let host = origin.host?.lowercased() ?? ""
        let sessionCookies = allCookies.filter { cookie in
            cookie.name == "minjaz_session" && cookie.isSecure &&
            cookie.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")).lowercased() == host &&
            (cookie.path == "/" || "/api/v1/".hasPrefix(cookie.path)) &&
            (cookie.expiresDate == nil || cookie.expiresDate! > Date())
        }
        guard !sessionCookies.isEmpty else { throw NativeReadError.loginRequired }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 18)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(HTTPCookie.requestHeaderFields(with: sessionCookies)["Cookie"], forHTTPHeaderField: "Cookie")

        let config = URLSessionConfiguration.ephemeral
        config.httpShouldSetCookies = false
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: config, delegate: MinjazNoRedirects(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse,
              http.url?.scheme == "https",
              http.url?.host?.lowercased() == host,
              data.count < 1_500_000 else { throw NativeReadError.responseInvalid }
        if http.statusCode == 401 { throw NativeReadError.loginRequired }
        guard http.statusCode == 200,
              let dataObject = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw NativeReadError.responseInvalid
        }
        return dataObject
    }

    private func string(_ value: Any?) -> String {
        guard let value else { return "" }
        if value is NSNull { return "" }
        return String(describing: value).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func id(_ value: Any?) -> Int? {
        guard let value else { return nil }
        let number = (value as? NSNumber)?.intValue ?? Int(string(value)) ?? 0
        return number > 0 && number <= 999_999_999_999_999 ? number : nil
    }

    private func makeRecord(_ row: [String: Any], section: NativeSection) -> NativeRecord? {
        let key = section == .conversations ? "order_id" : "id"
        guard let identifier = id(row[key]) else { return nil }
        let title = string(row["title"])
        let body = string(row["body"])
        let status = string(row["status"])
        let date = string(row["created_at"])
        switch section {
        case .projects:
            guard !title.isEmpty else { return nil }
            let name = string(row["service_name"])
            let category = string(row["category_name"])
            return NativeRecord(id: identifier, title: title,
                                detail: !name.isEmpty ? name : category,
                                status: status, timestamp: date,
                                amount: nil, pending: false)
        case .orders:
            guard !title.isEmpty else { return nil }
            let party = account?.role == "freelancer" ? string(row["client_name"]) : string(row["freelancer_name"])
            let value = string(row["amount"])
            return NativeRecord(id: identifier, title: title, detail: party,
                                status: status, timestamp: date,
                                amount: value.isEmpty ? nil : value, pending: false)
        case .conversations:
            guard !title.isEmpty else { return nil }
            return NativeRecord(id: identifier, title: title,
                                detail: string(row["counterpart_name"]) + " · " + string(row["last_message"]),
                                status: status, timestamp: string(row["last_message_at"]),
                                amount: nil,
                                pending: ((row["unread_messages"] as? NSNumber)?.intValue ?? 0) > 0)
        case .notifications:
            guard !title.isEmpty else { return nil }
            return NativeRecord(id: identifier, title: title, detail: body,
                                status: string(row["kind"]), timestamp: date,
                                amount: nil, pending: row["read_at"] == nil || row["read_at"] is NSNull)
        case .account: return nil
        }
    }
}

struct MinjazNativeScreen: View {
    @ObservedObject var model: MinjazNativeWorkspace
    let section: NativeSection
    let openWorkflow: (String) -> Void
    let chooseSection: (NativeSection) -> Void

    private let accent = Color(red: 101/255, green: 88/255, blue: 245/255)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(section.title).font(.system(size: 24, weight: .heavy))
                        if let account = model.account {
                            Text(account.name + " · " + (account.role == "freelancer" ? "مستقل" : "عميل"))
                                .foregroundStyle(.secondary).font(.subheadline)
                        }
                    }
                    Spacer()
                    Button {
                        Task { await model.load(section) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .frame(width: 44, height: 44)
                            .background(.white, in: RoundedRectangle(cornerRadius: 14))
                    }
                    .accessibilityLabel("تحديث البيانات")
                }

                if model.isLoading {
                    ProgressView("جاري تحميل بياناتك…")
                        .frame(maxWidth: .infinity).padding(32)
                } else if model.loginRequired {
                    infoPanel(symbol: "lock.shield",
                              title: "سجّل الدخول للمتابعة",
                              message: "تحتاج إلى حساب مفعّل بالبريد لعرض مشاريعك وعروضك وطلباتك.")
                    primary("تسجيل الدخول أو إنشاء حساب") { openWorkflow("/signup?auth=login") }
                } else if let error = model.error {
                    infoPanel(symbol: "wifi.exclamationmark", title: "تعذر التحميل", message: error)
                    primary("إعادة المحاولة") { Task { await model.load(section) } }
                } else if section == .account {
                    accountContent
                } else {
                    if section == .projects {
                        primary("نشر مشروع جديد") {
                            openWorkflow("/workspace#tasks-section")
                        }
                    }
                    if model.records.isEmpty {
                        infoPanel(symbol: section.icon,
                                  title: "لا توجد بيانات حاليًا",
                                  message: "ستظهر هنا بياناتك الفعلية بمجرد توفرها في مِنجاز.")
                    } else {
                        LazyVStack(spacing: 12) {
                            ForEach(model.records) { record in
                                Button {
                                    // Complex writes, payments and disputes keep
                                    // their real role-gated workspace for now.
                                    openWorkflow(section == .projects
                                        ? "/workspace#tasks-section" :
                                        section == .orders ? "/workspace#orders-section" :
                                        section == .conversations ? "/workspace#messages-section" :
                                            "/workspace#notifications-section")
                                } label: {
                                    HStack(alignment: .top, spacing: 12) {
                                        Image(systemName: section.icon)
                                            .font(.title3).foregroundStyle(accent)
                                            .frame(width: 35, height: 35)
                                            .background(accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
                                        VStack(alignment: .leading, spacing: 6) {
                                            HStack {
                                                Text(record.title).font(.subheadline.bold())
                                                    .lineLimit(2).foregroundStyle(.primary)
                                                if record.pending {
                                                    Circle().fill(accent).frame(width: 8, height: 8)
                                                }
                                            }
                                            if !record.detail.isEmpty {
                                                Text(record.detail).font(.caption)
                                                    .foregroundStyle(.secondary).lineLimit(3)
                                            }
                                            HStack {
                                                if !record.status.isEmpty {
                                                    Text(record.status)
                                                        .font(.caption2).foregroundStyle(accent)
                                                }
                                                Spacer()
                                                if let amount = record.amount {
                                                    Text(amount + " ر.س")
                                                        .font(.caption.bold()).foregroundStyle(.primary)
                                                }
                                            }
                                        }
                                        Spacer(minLength: 0)
                                        Image(systemName: "chevron.left")
                                            .font(.caption).foregroundStyle(.tertiary)
                                    }
                                    .padding(15)
                                    .background(.white, in: RoundedRectangle(cornerRadius: 16))
                                }.buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(Color(red: 0.97, green: 0.97, blue: 0.98))
        .refreshable { await model.load(section) }
        .task(id: section.rawValue) { await model.load(section) }
    }

    private var accountContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let account = model.account {
                VStack(alignment: .leading, spacing: 9) {
                    Text(account.name).font(.title3.bold())
                    Text(account.email).font(.subheadline).foregroundStyle(.secondary)
                    Text(account.verified ? "البريد الإلكتروني مفعل" : "البريد غير مفعل")
                        .font(.caption).foregroundStyle(account.verified ? .green : .orange)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
                .background(.white, in: RoundedRectangle(cornerRadius: 18))
            }
            action("المحادثات", icon: "bubble.left.and.bubble.right") {
                chooseSection(.conversations)
            }
            action("الإشعارات", icon: "bell") {
                chooseSection(.notifications)
            }
            action("الملف الشخصي وتغيير الدور", icon: "person.text.rectangle") {
                openWorkflow("/workspace#profile")
            }
            action("سياسة الخصوصية", icon: "hand.raised") {
                openWorkflow("/privacy")
            }
            action("حذف الحساب", icon: "trash") {
                openWorkflow("/account-deletion")
            }
        }
    }

    private func action(_ title: String, icon: String, run: @escaping () -> Void) -> some View {
        Button(action: run) {
            HStack(spacing: 12) {
                Image(systemName: icon).foregroundStyle(accent)
                    .frame(width: 32)
                Text(title).font(.subheadline.bold()).foregroundStyle(.primary)
                Spacer()
                Image(systemName: "chevron.left").foregroundStyle(.tertiary)
            }
            .padding(17).background(.white, in: RoundedRectangle(cornerRadius: 15))
        }.buttonStyle(.plain)
    }

    private func primary(_ title: String, run: @escaping () -> Void) -> some View {
        Button(action: run) {
            Text(title).frame(maxWidth: .infinity).padding(14)
                .background(accent, in: RoundedRectangle(cornerRadius: 13))
                .foregroundStyle(.white).font(.subheadline.bold())
        }.buttonStyle(.plain)
    }

    private func infoPanel(symbol: String, title: String, message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.largeTitle).foregroundStyle(accent)
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity).padding(27)
        .background(.white, in: RoundedRectangle(cornerRadius: 18))
    }
}
