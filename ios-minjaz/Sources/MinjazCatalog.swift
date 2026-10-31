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
            categories = parents
            services = children
            if parents.isEmpty { error = "لم تتوفر الأقسام بعد." }
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
        guard let response = response as? HTTPURLResponse,
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
    private let blue = Color(red: 0.29, green: 0.32, blue: 0.84)

    private var filtered: [MinjazService] {
        catalog.services.filter { item in
            (selectedCategory == nil || item.category_id == selectedCategory) &&
            (keyword.isEmpty || item.name_ar.localizedStandardContains(keyword) ||
             (item.client_guidance ?? "").localizedStandardContains(keyword))
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("تخصصات تناسب مشروعك")
                        .font(.system(size: 25, weight: .heavy))
                    Text("ابحث عن نوع الخدمة، وبعدها انشر مشروعك ليقدم المستقلون عروضهم.")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                .padding(.top, 18)

                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("ابحث في التخصصات", text: $keyword)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityLabel("البحث في التخصصات")
                    if !keyword.isEmpty {
                        Button { keyword = "" } label: {
                            Image(systemName: "xmark.circle.fill")
                        }.accessibilityLabel("مسح البحث")
                    }
                }
                .padding(13)
                .background(.white, in: RoundedRectangle(cornerRadius: 14))

                if catalog.loading {
                    HStack(spacing: 10) {
                        ProgressView()
                        Text("جاري تحميل الأقسام…")
                    }.frame(maxWidth: .infinity).padding(30)
                } else if let error = catalog.error {
                    VStack(spacing: 12) {
                        Text(error).multilineTextAlignment(.center)
                        Button("إعادة المحاولة") {
                            Task { await catalog.retry() }
                        }.buttonStyle(.borderedProminent)
                    }
                    .frame(maxWidth: .infinity).padding(24)
                    .background(.white, in: RoundedRectangle(cornerRadius: 16))
                } else {
                    Text("الأقسام الرئيسية").font(.headline)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            categoryButton(nil, name: "الكل")
                            ForEach(catalog.categories) { category in
                                categoryButton(category.id, name: category.name_ar)
                            }
                        }
                        .padding(.vertical, 2)
                    }

                    HStack {
                        Text("التخصصات").font(.headline)
                        Spacer()
                        Text("\(filtered.count) تخصص")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if filtered.isEmpty {
                        Text("لا توجد تخصصات مطابقة. غيّر كلمة البحث أو القسم.")
                            .frame(maxWidth: .infinity).padding(25)
                    }

                    LazyVStack(spacing: 10) {
                        ForEach(filtered) { service in
                            Button { onOpen(service) } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "briefcase.fill")
                                        .foregroundStyle(blue)
                                        .frame(width: 36, height: 36)
                                        .background(blue.opacity(0.09), in: RoundedRectangle(cornerRadius: 9))
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(service.name_ar)
                                            .foregroundStyle(.primary).font(.subheadline.bold())
                                        if let category = catalog.categories.first(where: { $0.id == service.category_id }) {
                                            Text(category.name_ar)
                                                .foregroundStyle(.secondary).font(.caption)
                                        }
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.left")
                                        .font(.caption.bold()).foregroundStyle(.tertiary)
                                }
                                .padding(14)
                                .background(.white, in: RoundedRectangle(cornerRadius: 14))
                            }
                            .buttonStyle(.plain)
                            .accessibilityHint("فتح مشاريع مِنجاز لهذا النوع من الخدمات")
                        }
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 25)
        }
        .background(Color(red: 0.97, green: 0.97, blue: 0.98))
    }

    private func categoryButton(_ id: Int?, name: String) -> some View {
        Button { selectedCategory = id } label: {
            Text(name)
                .font(.system(size: 12, weight: .semibold))
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(selectedCategory == id ? blue : .white,
                            in: Capsule())
                .foregroundStyle(selectedCategory == id ? Color.white : Color.primary)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selectedCategory == id ? .isSelected : [])
    }
}
