import SwiftUI

struct MinjazCategory: Decodable, Identifiable {
    let id: Int
    let name_ar: String
    let icon: String?
}

struct MinjazService: Decodable, Identifiable {
    let id: Int
    let category_id: Int
    let name_ar: String
    let client_guidance: String?
    let freelancer_guidance: String?
}

private struct APIItems<T: Decodable>: Decodable {
    let items: [T]
}

/// Truly native read-only public directory. Requests never create orders,
/// authenticate users, or initiate a payment.
@MainActor
final class MinjazCatalog: ObservableObject {
    @Published private(set) var categories: [MinjazCategory] = []
    @Published private(set) var services: [MinjazService] = []
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    private var host: URL?

    func load(origin: URL) async {
        if loading { return }
        host = origin
        loading = true
        error = nil
        defer { loading = false }
        do {
            let (parents, children): ([MinjazCategory], [MinjazService]) = try await (
                get("/api/v1/categories", origin: origin),
                get("/api/v1/services", origin: origin)
            )
            // The catalog is public, but it is still remote data. Reject
            // invalid identifiers, duplicates and orphan specialties before
            // presenting links that users might act on.
            let validCategories = parents.filter { item in
                item.id > 0 && item.id <= 999_999_999_999_999 &&
                !item.name_ar.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }.prefix(300)
            let categoryIDs = Set(validCategories.map(\.id))
            var serviceIDs = Set<Int>()
            let validServices = children.filter { item in
                item.id > 0 && item.id <= 999_999_999_999_999 &&
                categoryIDs.contains(item.category_id) &&
                !item.name_ar.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
                serviceIDs.insert(item.id).inserted
            }.prefix(500)
            categories = Array(validCategories)
            services = Array(validServices)
            if categories.isEmpty { error = "لم تتوفر الأقسام بعد." }
        } catch {
            self.error = "تعذر تحميل التخصصات. تحقق من اتصالك وحاول مجددًا."
        }
    }

    func retry() async {
        guard let host else { return }
        await load(origin: host)
    }

    private func get<T: Decodable>(_ path: String, origin: URL) async throws -> [T] {
        guard let url = URL(string: path, relativeTo: origin)?.absoluteURL,
              url.scheme == "https", url.host == origin.host else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        // URLSession follows redirects by default. Never accept catalog JSON
        // from an off-domain redirect, even if its schema looks legitimate.
        guard let response = response as? HTTPURLResponse,
              let finalURL = response.url,
              finalURL.scheme == "https",
              finalURL.host?.lowercased() == origin.host?.lowercased(),
              (finalURL.port == nil || finalURL.port == 443),
              finalURL.user == nil, finalURL.password == nil,
              response.statusCode == 200, data.count < 1_500_000 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(APIItems<T>.self, from: data).items
    }
}

struct CatalogView: View {
    @ObservedObject var catalog: MinjazCatalog
    let onOpen: (MinjazService) -> Void

    @State private var keyword = ""
    @State private var selectedCategory: Int?
    @State private var chosenService: MinjazService?
    @State private var pendingOpen: MinjazService?

    private var filtered: [MinjazService] {
        let term = keyword.trimmingCharacters(in: .whitespacesAndNewlines)
        return catalog.services.filter { item in
            (selectedCategory == nil || item.category_id == selectedCategory) &&
            (term.isEmpty || item.name_ar.localizedStandardContains(term) ||
             (item.client_guidance ?? "").localizedStandardContains(term) ||
             (catalog.categories.first(where: { $0.id == item.category_id })?.name_ar ?? "")
                .localizedStandardContains(term))
        }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                introduction
                searchInput

                if catalog.loading {
                    HStack(spacing: 12) {
                        ProgressView().tint(MinjazUI.primary)
                        Text("جاري تحميل الأقسام…")
                            .font(MinjazUI.body()).foregroundStyle(MinjazUI.muted)
                    }
                    .frame(maxWidth: .infinity).padding(28)
                } else if let error = catalog.error {
                    MinjazSurface {
                        VStack(spacing: 12) {
                            Image(systemName: "wifi.exclamationmark")
                                .font(.title).foregroundStyle(MinjazUI.primary)
                            Text(error).multilineTextAlignment(.center)
                                .font(MinjazUI.body())
                            Button("إعادة المحاولة") { Task { await catalog.retry() } }
                                .buttonStyle(.borderedProminent).tint(MinjazUI.primary)
                        }
                        .padding(22)
                        .frame(maxWidth: .infinity)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeading("الأقسام الرئيسية")
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                categoryButton(nil, name: "الكل")
                                ForEach(catalog.categories) { category in
                                    categoryButton(category.id, name: category.name_ar)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    HStack(alignment: .firstTextBaseline) {
                        sectionHeading("التخصصات")
                        Spacer(minLength: 8)
                        Text("\(filtered.count) تخصص")
                            .font(MinjazUI.body(13)).foregroundStyle(MinjazUI.muted)
                            .monospacedDigit()
                    }
                    if filtered.isEmpty {
                        MinjazSurface {
                            VStack(spacing: 8) {
                                Image(systemName: "magnifyingglass")
                                    .font(.title).foregroundStyle(MinjazUI.primary)
                                Text("لا توجد تخصصات مطابقة")
                                    .font(MinjazUI.body(16, weight: .semibold))
                                Text("جرّب تغيير القسم أو عبارة البحث")
                                    .font(MinjazUI.body(14)).foregroundStyle(MinjazUI.muted)
                            }
                            .frame(maxWidth: .infinity).padding(30)
                        }
                    } else {
                        LazyVStack(spacing: 10) {
                            ForEach(filtered) { service in
                                serviceRow(service)
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, 17)
            .padding(.top, 22)
            .padding(.bottom, 28)
        }
        .background(MinjazUI.canvas)
        .scrollDismissesKeyboard(.interactively)
        .sheet(item: $chosenService, onDismiss: {
            if let service = pendingOpen {
                pendingOpen = nil
                onOpen(service)
            }
        }) { service in
            MinjazSpecialtyDetails(
                service: service,
                categoryName: catalog.categories.first(where: { $0.id == service.category_id })?.name_ar ?? "",
                onContinue: {
                    pendingOpen = service
                    chosenService = nil
                }
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    private var introduction: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 9) {
                    Text("تخصصات تناسب مشروعك")
                        .font(MinjazUI.heading(25))
                        .foregroundStyle(MinjazUI.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("ابحث عن نوع الخدمة، ثم انشر مشروعك ليتقدم المستقلون بعروضهم.")
                        .font(MinjazUI.body(14))
                        .foregroundStyle(MinjazUI.muted)
                        .lineSpacing(5)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                Image(systemName: "briefcase.fill")
                    .font(.system(size: 27, weight: .medium))
                    .foregroundStyle(MinjazUI.primary)
                    .frame(width: 56, height: 56)
                    .background(MinjazUI.tinted, in: RoundedRectangle(cornerRadius: 17))
                    .accessibilityHidden(true)
            }
        }
        .padding(18)
        .background(
            LinearGradient(colors: [.white, MinjazUI.tinted.opacity(0.72)],
                           startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: 22)
        )
    }

    private var searchInput: some View {
        HStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 18, weight: .medium))
                .foregroundStyle(MinjazUI.primary)
                .frame(width: 37, height: 37)
                .background(MinjazUI.tinted, in: RoundedRectangle(cornerRadius: 11))
            TextField("ابحث في التخصصات", text: $keyword)
                .font(MinjazUI.body(15))
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.search)
                .accessibilityLabel("البحث في التخصصات")
            if !keyword.isEmpty {
                Button { keyword = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(MinjazUI.muted)
                }
                .accessibilityLabel("مسح البحث")
            }
        }
        .padding(.horizontal, 13)
        .frame(minHeight: 55)
        .background(.white, in: RoundedRectangle(cornerRadius: 17))
        .overlay(
            RoundedRectangle(cornerRadius: 17)
                .stroke(MinjazUI.border, lineWidth: 1)
        )
    }

    private func sectionHeading(_ title: String) -> some View {
        Text(title).font(MinjazUI.heading(19))
            .foregroundStyle(MinjazUI.ink)
    }

    private func serviceRow(_ service: MinjazService) -> some View {
        Button { chosenService = service } label: {
            MinjazSurface {
                HStack(spacing: 13) {
                    Image(systemName: "briefcase")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(MinjazUI.primary)
                        .frame(width: 46, height: 46)
                        .background(MinjazUI.tinted, in: RoundedRectangle(cornerRadius: 13))
                        .accessibilityHidden(true)

                    VStack(alignment: .leading, spacing: 6) {
                        Text(service.name_ar)
                            .font(MinjazUI.body(15, weight: .semibold))
                            .foregroundStyle(MinjazUI.ink)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                        if let category = catalog.categories.first(where: { $0.id == service.category_id }) {
                            Text(category.name_ar)
                                .font(MinjazUI.body(12))
                                .foregroundStyle(MinjazUI.muted)
                                .lineLimit(1)
                        }
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.left")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(MinjazUI.muted.opacity(0.65))
                        .accessibilityHidden(true)
                }
                .padding(.horizontal, 15)
                .padding(.vertical, 14)
                .frame(maxWidth: .infinity, minHeight: 82, alignment: .leading)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(service.name_ar)
        .accessibilityHint("عرض المشاريع ونشر طلب في هذا التخصص")
    }

    private func categoryButton(_ id: Int?, name: String) -> some View {
        let isSelected = selectedCategory == id
        return Button { selectedCategory = id } label: {
            Text(name)
                .font(MinjazUI.body(13, weight: .semibold))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 16)
                .frame(minHeight: 43)
                .foregroundStyle(isSelected ? .white : MinjazUI.ink)
                .background(isSelected ? MinjazUI.primary : .white, in: Capsule())
                .overlay(Capsule().stroke(isSelected ? MinjazUI.primary : MinjazUI.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
