import Foundation
import SwiftUI
import WebKit
import UniformTypeIdentifiers

struct SharedMinjazFile: Identifiable {
    let id = UUID()
    let url: URL
}

/// Native browser for authenticated first-party marketplace workflows.
/// Sessions stay in WebKit's persistent first-party cookie store; no auth
/// tokens are copied to JavaScript bridges, logs, or device preferences.
final class MinjazBrowser: NSObject, ObservableObject {
    @Published var isLoading = false
    @Published var error: String?
    @Published var shareFile: SharedMinjazFile?

    let origin: URL
    let webView: WKWebView

    private var openPanel: (([URL]?) -> Void)?
    private var downloadDestinations: [ObjectIdentifier: URL] = [:]

    override init() {
        let raw = (Bundle.main.object(forInfoDictionaryKey: "MinjazBaseURL") as? String) ?? ""
        guard let url = URL(string: raw), url.scheme == "https",
              url.user == nil, url.password == nil, url.query == nil,
              url.fragment == nil,
              let host = url.host, !host.isEmpty,
              (url.path.isEmpty || url.path == "/") else {
            preconditionFailure("MINJAZ HTTPS origin must be configured in Info.plist")
        }
        #if DEBUG
        precondition(host == "beta.minjazapp.com", "iOS debug must not use production")
        #else
        precondition(host == "minjaz-app-prod-production.up.railway.app",
                     "iOS release must not use preview")
        #endif
        self.origin = url
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.allowsInlineMediaPlayback = true
        self.webView = WKWebView(frame: .zero, configuration: configuration)
        super.init()
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.scrollView.isScrollEnabled = true
        #if DEBUG
        if #available(iOS 16.4, *) { webView.isInspectable = true }
        #endif
        open(path: "/workspace")
    }

    func open(path: String) {
        guard path.hasPrefix("/"), !path.hasPrefix("//"),
              !path.contains("\\"), !path.contains("://"),
              let url = URL(string: path, relativeTo: origin)?.absoluteURL,
              isFirstParty(url) else { return }
        error = nil
        webView.load(URLRequest(url: url,
                                cachePolicy: .useProtocolCachePolicy,
                                timeoutInterval: 25))
    }

    func reload() {
        error = nil
        if webView.url == nil { open(path: "/workspace") }
        else { webView.reload() }
    }

    private func isFirstParty(_ url: URL) -> Bool {
        return url.scheme == "https" && url.host?.lowercased() == origin.host?.lowercased()
            && (url.port == nil || url.port == 443)
            && url.user == nil && url.password == nil
    }

    private func showSystemLink(_ url: URL) {
        guard let scheme = url.scheme?.lowercased(),
              ["https", "http", "mailto", "tel"].contains(scheme) else { return }
        if scheme == "https" || scheme == "http" {
            guard url.host != nil, url.user == nil, url.password == nil else { return }
        }
        UIApplication.shared.open(url)
    }

    private func presenter() -> UIViewController? {
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
        var controller = windows.first(where: { $0.isKeyWindow })?.rootViewController
        while let presented = controller?.presentedViewController { controller = presented }
        return controller
    }
}

extension MinjazBrowser: WKNavigationDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else {
            decisionHandler(.cancel); return
        }
        if isFirstParty(url) {
            if action.shouldPerformDownload { decisionHandler(.download) }
            else { decisionHandler(.allow) }
            return
        }
        if url.absoluteString == "about:blank" || url.scheme == "blob" {
            decisionHandler(.allow); return
        }
        // Off-domain URLs and presigned storage links cannot access app cookies.
        // They open in Safari/system apps; local, file and JS schemes are refused.
        showSystemLink(url)
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if response.isForMainFrame, let http = response.response as? HTTPURLResponse,
           http.statusCode >= 500 {
            error = "تعذر الوصول إلى مِنجاز حاليًا. حاول التحديث."
            isLoading = false
            decisionHandler(.cancel)
            return
        }
        if !response.canShowMIMEType { decisionHandler(.download) }
        else { decisionHandler(.allow) }
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        error = nil
        isLoading = true
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        error = nil
        isLoading = false
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        isLoading = false
        if (error as NSError).code != NSURLErrorCancelled {
            self.error = "الاتصال غير متاح. تأكد من الإنترنت وأعد المحاولة."
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!,
                 withError error: Error) {
        isLoading = false
        if (error as NSError).code != NSURLErrorCancelled {
            self.error = "تعذر فتح الصفحة. حاول مرة أخرى."
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        error = "توقفت الصفحة عن العمل. يمكنك إعادة تحميلها."
        isLoading = false
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction,
                 didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse,
                 didBecome download: WKDownload) {
        download.delegate = self
    }
}

extension MinjazBrowser: WKUIDelegate, UIDocumentPickerDelegate {
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let url = navigationAction.request.url else { return nil }
        if isFirstParty(url) { webView.load(navigationAction.request) }
        else { showSystemLink(url) }
        return nil
    }

    @available(iOS 18.4, *)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping ([URL]?) -> Void) {
        guard openPanel == nil, let presenter = presenter() else {
            completionHandler(nil); return
        }
        openPanel = completionHandler
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.item], asCopy: true)
        picker.allowsMultipleSelection = parameters.allowsMultipleSelection
        picker.delegate = self
        presenter.present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        let done = openPanel
        openPanel = nil
        done?(urls)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        let done = openPanel
        openPanel = nil
        done?(nil)
    }

    private func alert(_ message: String, completion: @escaping (Bool) -> Void,
                       confirmation: Bool) {
        guard let controller = presenter() else { completion(false); return }
        let alert = UIAlertController(title: "مِنجاز", message: message, preferredStyle: .alert)
        if confirmation {
            alert.addAction(UIAlertAction(title: "إلغاء", style: .cancel) { _ in completion(false) })
        }
        alert.addAction(UIAlertAction(title: "موافق", style: .default) { _ in completion(true) })
        controller.present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        alert(message, completion: { _ in completionHandler() }, confirmation: false)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        alert(message, completion: completionHandler, confirmation: true)
    }
}

extension MinjazBrowser: WKDownloadDelegate {
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        // Never use untrusted filename as a path. Files are temporary and shared
        // through the iOS share sheet, never opened with elevated privileges.
        let filename = (suggestedFilename as NSString).lastPathComponent
            .replacingOccurrences(of: "/", with: "_")
        let safeName = filename.isEmpty ? "minjaz-download" : String(filename.prefix(100))
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("minjaz-" + UUID().uuidString, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory,
                                                    withIntermediateDirectories: true)
            let destination = directory.appendingPathComponent(safeName)
            downloadDestinations[ObjectIdentifier(download)] = destination
            completionHandler(destination)
        } catch {
            completionHandler(nil)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let location = downloadDestinations.removeValue(forKey: ObjectIdentifier(download)) {
            shareFile = SharedMinjazFile(url: location)
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error,
                  resumeData: Data?) {
        downloadDestinations.removeValue(forKey: ObjectIdentifier(download))
        self.error = "تعذر تحميل الملف. حاول مجددًا."
    }
}

struct MinjazWebView: UIViewRepresentable {
    @ObservedObject var browser: MinjazBrowser
    func makeUIView(context: Context) -> WKWebView { browser.webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
