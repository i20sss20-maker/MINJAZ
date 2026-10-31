import SwiftUI

/// Fully native, read-only specialty sheet. Creating a project is still
/// delegated to the existing authenticated, role-aware server workflow.
struct MinjazSpecialtyDetails: View {
    let service: MinjazService
    let categoryName: String
    let onContinue: () -> Void
    @Environment(\.dismiss) private var dismiss

    private func clean(_ value: String?) -> String {
        String((value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).prefix(1200))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "briefcase.fill")
                        .font(.system(size: 25, weight: .semibold))
                        .foregroundStyle(MinjazUI.primary)
                        .frame(width: 57, height: 57)
                        .background(MinjazUI.tinted, in: RoundedRectangle(cornerRadius: 17))
                    VStack(alignment: .leading, spacing: 7) {
                        Text(service.name_ar)
                            .font(MinjazUI.heading(22))
                            .foregroundStyle(MinjazUI.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(categoryName)
                            .font(MinjazUI.body(13, weight: .medium))
                            .foregroundStyle(MinjazUI.muted)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.top, 14)

                if !clean(service.client_guidance).isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("ما الذي تحتاجه؟", systemImage: "checklist")
                            .font(MinjazUI.heading(17))
                            .foregroundStyle(MinjazUI.ink)
                        Text(clean(service.client_guidance))
                            .font(MinjazUI.body(15))
                            .foregroundStyle(MinjazUI.muted)
                            .lineSpacing(5)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(17)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.white, in: RoundedRectangle(cornerRadius: 18))
                }

                if !clean(service.freelancer_guidance).isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("للمستقل", systemImage: "person.crop.rectangle")
                            .font(MinjazUI.heading(17))
                            .foregroundStyle(MinjazUI.ink)
                        Text(clean(service.freelancer_guidance))
                            .font(MinjazUI.body(15))
                            .foregroundStyle(MinjazUI.muted)
                            .lineSpacing(5)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(17)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.white, in: RoundedRectangle(cornerRadius: 18))
                }

                Text("سيُتحقق من صلاحية حسابك ومن توفر التخصص قبل إرسال أي طلب.")
                    .font(MinjazUI.body(12))
                    .foregroundStyle(MinjazUI.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 19)
            .padding(.bottom, 22)
        }
        .safeAreaInset(edge: .bottom) {
            Button(action: onContinue) {
                HStack {
                    Spacer()
                    Text("متابعة إلى المشروع")
                        .font(MinjazUI.body(16, weight: .bold))
                    Image(systemName: "arrow.left")
                    Spacer()
                }
                .padding(16)
                .foregroundStyle(.white)
                .background(MinjazUI.primary, in: RoundedRectangle(cornerRadius: 16))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 18)
            .padding(.vertical, 13)
            .background(.regularMaterial)
        }
        .background(MinjazUI.canvas)
        .accessibilityElement(children: .contain)
    }
}
