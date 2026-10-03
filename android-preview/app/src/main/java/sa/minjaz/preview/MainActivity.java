package sa.minjaz.preview;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Environment;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.URLUtil;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Locale;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://minjaz-app-prod-production.up.railway.app";
    private static final String APP_HOST = "minjaz-app-prod-production.up.railway.app";
    private static final int FILE_CHOOSER_REQUEST = 7001;
    private static final long PAGE_LOAD_TIMEOUT_MS = 20000L;

    private FrameLayout root;
    private WebView webView;
    private View errorView;
    private ValueCallback<Uri[]> fileCallback;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private Runnable pageLoadTimeout;
    private int pageLoadGeneration = 0;
    private String lastGoodUrl;
    private boolean backHandling = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        applySystemChrome();

        buildUi();
        configureWebView();
        registerNetworkRecovery();

        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                this::handleBack
            );
        }

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            loadLaunchDestination(getIntent());
        }
    }

    private void buildUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(surfaceColor());

        webView = new WebView(this);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));
        root.addView(webView);

        errorView = buildErrorView();
        errorView.setVisibility(View.GONE);
        root.addView(errorView, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));

        if (Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.statusBars()
                        | WindowInsets.Type.navigationBars()
                        | WindowInsets.Type.displayCutout()
                );
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }

        setContentView(root);
    }

    private View buildErrorView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(28), dp(28), dp(28), dp(28));
        box.setBackgroundColor(surfaceColor());

        TextView title = new TextView(this);
        title.setText(getString(R.string.connection_error_title));
        title.setTextSize(20);
        title.setTextColor(primaryTextColor());
        title.setGravity(Gravity.CENTER);
        box.addView(title);

        TextView message = new TextView(this);
        message.setText(getString(R.string.connection_error_message));
        message.setTextSize(14);
        message.setTextColor(secondaryTextColor());
        message.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams messageParams = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
        messageParams.topMargin = dp(10);
        box.addView(message, messageParams);

        Button retry = new Button(this);
        retry.setText(getString(R.string.retry));
        retry.setOnClickListener(v -> retryCurrentPage());
        LinearLayout.LayoutParams retryParams = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            dp(48)
        );
        retryParams.topMargin = dp(18);
        box.addView(retry, retryParams);

        return box;
    }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setTextZoom(100);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setUserAgentString(settings.getUserAgentString() + " MINJAZ-Android/0.10");

        if (Build.VERSION.SDK_INT >= 26) {
            settings.setSafeBrowsingEnabled(true);
        }

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, false);

        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setBackgroundColor(surfaceColor());

        webView.setWebViewClient(
            Build.VERSION.SDK_INT >= 26
                ? new Api26MinjazWebViewClient()
                : new MinjazWebViewClient()
        );

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                WebView view,
                ValueCallback<Uri[]> callback,
                FileChooserParams params
            ) {
                if (fileCallback != null) {
                    fileCallback.onReceiveValue(null);
                }
                fileCallback = callback;
                Intent intent = params.createIntent();
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
            }
        });

        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            Uri uri = Uri.parse(url);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
            if ("https".equals(scheme)) {
                enqueueDownload(url, userAgent, contentDisposition, mimeType);
            } else {
                openExternal(uri);
            }
        });
    }

    private void loadLaunchDestination(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (isInternalUri(data)) {
            webView.loadUrl(localizedInternalUrl(data));
        } else {
            webView.loadUrl(appUrlWithLocale());
            if (data != null) openExternal(data);
        }
    }

    private boolean isInternalUri(Uri uri) {
        if (uri == null) return false;
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        String host = uri.getHost() == null ? "" : uri.getHost();
        return "https".equals(scheme) && APP_HOST.equalsIgnoreCase(host);
    }

    private boolean handleNavigation(Uri uri) {
        if (uri == null) return false;
        if (isInternalUri(uri)) return false;

        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        if ("about".equals(scheme) || "data".equals(scheme) || "blob".equals(scheme)) {
            return false;
        }

        if ("intent".equals(scheme)) {
            try {
                Intent intent = Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME);
                intent.addCategory(Intent.CATEGORY_BROWSABLE);
                intent.setComponent(null);
                intent.setSelector(null);
                try {
                    startActivity(intent);
                } catch (ActivityNotFoundException missing) {
                    String fallback = intent.getStringExtra("browser_fallback_url");
                    if (fallback != null && !fallback.trim().isEmpty()) {
                        openExternal(Uri.parse(fallback));
                    }
                }
            } catch (Exception ignored) {
            }
            return true;
        }

        openExternal(uri);
        return true;
    }

    private void enqueueDownload(
        String url,
        String userAgent,
        String contentDisposition,
        String mimeType
    ) {
        try {
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            String fileName = safeDownloadName(
                URLUtil.guessFileName(url, contentDisposition, mimeType)
            );

            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null && !cookie.trim().isEmpty()) {
                request.addRequestHeader("Cookie", cookie);
            }
            if (userAgent != null && !userAgent.trim().isEmpty()) {
                request.addRequestHeader("User-Agent", userAgent);
            }

            if (mimeType != null && !mimeType.trim().isEmpty()) {
                request.setMimeType(mimeType);
            }

            request.setTitle(fileName);
            request.setDescription(getString(R.string.app_name));
            request.setAllowedOverMetered(true);
            request.setAllowedOverRoaming(false);
            request.setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
            );

            if (Build.VERSION.SDK_INT >= 29) {
                request.setDestinationInExternalPublicDir(
                    Environment.DIRECTORY_DOWNLOADS,
                    fileName
                );
            } else {
                request.setDestinationInExternalFilesDir(
                    this,
                    Environment.DIRECTORY_DOWNLOADS,
                    fileName
                );
            }

            DownloadManager manager =
                (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            if (manager != null) {
                manager.enqueue(request);
            } else {
                openExternal(Uri.parse(url));
            }
        } catch (Exception e) {
            openExternal(Uri.parse(url));
        }
    }

    private String safeDownloadName(String raw) {
        String name = raw == null ? "minjaz-file" : raw.trim();
        if (name.isEmpty()) name = "minjaz-file";
        name = name.replaceAll("[\\\\/:*?\"<>|]", "_");
        if (name.length() > 120) {
            int dot = name.lastIndexOf('.');
            String ext = dot > 0 && name.length() - dot <= 12 ? name.substring(dot) : "";
            name = name.substring(0, Math.min(100, name.length())) + ext;
        }
        return name;
    }

    private void openExternal(Uri uri) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, uri);
            intent.addCategory(Intent.CATEGORY_BROWSABLE);
            startActivity(intent);
        } catch (ActivityNotFoundException ignored) {
        }
    }

    private class MinjazWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            if (!request.isForMainFrame()) return false;
            return handleNavigation(request.getUrl());
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            super.onPageStarted(view, url, favicon);
            if (url != null && isInternalUri(Uri.parse(url))) {
                schedulePageLoadTimeout(url);
            } else {
                cancelPageLoadTimeout();
            }
        }

        @Override
        public void onPageCommitVisible(WebView view, String url) {
            cancelPageLoadTimeout();
            if (url != null) {
                try {
                    Uri uri = Uri.parse(url);
                    if (isInternalUri(uri)) lastGoodUrl = localizedInternalUrl(uri);
                } catch (Exception ignored) {
                }
            }
            hideError();
            super.onPageCommitVisible(view, url);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            cancelPageLoadTimeout();
            super.onPageFinished(view, url);
        }

        @Override
        public void onReceivedError(
            WebView view,
            WebResourceRequest request,
            WebResourceError error
        ) {
            if (request.isForMainFrame()) {
                cancelPageLoadTimeout();
                showError();
            }
            super.onReceivedError(view, request, error);
        }

        @Override
        public void onReceivedHttpError(
            WebView view,
            WebResourceRequest request,
            WebResourceResponse errorResponse
        ) {
            if (request.isForMainFrame() && errorResponse.getStatusCode() >= 400) {
                cancelPageLoadTimeout();
                showError();
            }
            super.onReceivedHttpError(view, request, errorResponse);
        }
    }

    private class Api26MinjazWebViewClient extends MinjazWebViewClient {
        @Override
        public boolean onRenderProcessGone(
            WebView view,
            RenderProcessGoneDetail detail
        ) {
            recoverWebView();
            return true;
        }
    }

    private void registerNetworkRecovery() {
        connectivityManager =
            (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (connectivityManager == null || Build.VERSION.SDK_INT < 24) return;

        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                runOnUiThread(() -> mainHandler.postDelayed(() -> {
                    if (webView != null && errorView != null
                        && errorView.getVisibility() == View.VISIBLE) {
                        retryCurrentPage();
                    }
                }, 500));
            }
        };

        try {
            connectivityManager.registerDefaultNetworkCallback(networkCallback);
        } catch (Exception ignored) {
            networkCallback = null;
        }
    }

    private void recoverWebView() {
        cancelPageLoadTimeout();
        String current = webView != null ? webView.getUrl() : null;
        final String lastUrl = safeInternalUrl(current)
            ? localizedInternalUrl(Uri.parse(current))
            : (safeInternalUrl(lastGoodUrl) ? lastGoodUrl : appUrlWithLocale());

        if (webView != null) {
            root.removeView(webView);
            try {
                webView.destroy();
            } catch (Exception ignored) {
            }
        }

        webView = new WebView(this);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));
        root.addView(webView, 0);
        configureWebView();
        hideError();
        webView.loadUrl(lastUrl);
    }

    private void showError() {
        if (errorView != null) errorView.setVisibility(View.VISIBLE);
    }

    private void hideError() {
        if (errorView != null) errorView.setVisibility(View.GONE);
    }

    private boolean safeInternalUrl(String url) {
        if (url == null || url.trim().isEmpty()) return false;
        try {
            return isInternalUri(Uri.parse(url));
        } catch (Exception ignored) {
            return false;
        }
    }

    private void retryCurrentPage() {
        if (webView == null) return;
        hideError();
        cancelPageLoadTimeout();
        String current = webView.getUrl();
        String target = safeInternalUrl(current)
            ? localizedInternalUrl(Uri.parse(current))
            : (safeInternalUrl(lastGoodUrl) ? lastGoodUrl : appUrlWithLocale());
        webView.stopLoading();
        webView.loadUrl(target);
    }

    private void schedulePageLoadTimeout(String url) {
        cancelPageLoadTimeout();
        final int generation = ++pageLoadGeneration;
        pageLoadTimeout = () -> {
            if (generation != pageLoadGeneration || webView == null) return;
            String current = webView.getUrl();
            if (safeInternalUrl(current) || safeInternalUrl(url)) {
                showError();
            }
        };
        mainHandler.postDelayed(pageLoadTimeout, PAGE_LOAD_TIMEOUT_MS);
    }

    private void cancelPageLoadTimeout() {
        pageLoadGeneration++;
        if (pageLoadTimeout != null) {
            mainHandler.removeCallbacks(pageLoadTimeout);
            pageLoadTimeout = null;
        }
    }

    private boolean isNetworkReady() {
        if (connectivityManager == null) return true;
        try {
            Network network = connectivityManager.getActiveNetwork();
            if (network == null) return false;
            NetworkCapabilities caps = connectivityManager.getNetworkCapabilities(network);
            return caps != null
                && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
        } catch (Exception ignored) {
            return true;
        }
    }

    private void nativeBackFallback() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            finish();
        }
    }

    private void handleBack() {
        if (backHandling) return;
        if (errorView != null && errorView.getVisibility() == View.VISIBLE) {
            hideError();
            return;
        }
        if (webView == null) {
            finish();
            return;
        }
        backHandling = true;
        String script = "(function(){try{"
            + "var g=document.getElementById('globalSearchOverlayV28');"
            + "if(g&&g.classList.contains('on')&&window.closeGlobalSearchV28){window.closeGlobalSearchV28();return true;}"
            + "var o=document.getElementById('modalOverlay');"
            + "if(o&&o.classList.contains('on')&&window.closeModal){window.closeModal();return true;}"
            + "var p=document.querySelector('.page.on');"
            + "if(p&&p.id&&p.id!=='home'&&window.go){window.go('home');return true;}"
            + "return false;}catch(e){return false;}})();";
        webView.evaluateJavascript(script, value -> {
            backHandling = false;
            if (!"true".equals(value)) nativeBackFallback();
        });
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        Uri data = intent == null ? null : intent.getData();
        if (isInternalUri(data)) {
            webView.loadUrl(localizedInternalUrl(data));
        } else if (data != null) {
            openExternal(data);
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (Build.VERSION.SDK_INT < 33) {
            handleBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        applySystemChrome();
        if (webView != null) {
            webView.onResume();
            if (errorView != null && errorView.getVisibility() == View.VISIBLE && isNetworkReady()) {
                mainHandler.postDelayed(this::retryCurrentPage, 350);
                return;
            }
            String current = webView.getUrl();
            if (current == null && webView.copyBackForwardList().getSize() == 0) {
                loadLaunchDestination(getIntent());
            } else if (current != null) {
                try {
                    Uri currentUri = Uri.parse(current);
                    if (isInternalUri(currentUri)) {
                        String localized = localizedInternalUrl(currentUri);
                        if (!current.equals(localized)) {
                            webView.loadUrl(localized);
                        }
                    }
                } catch (Exception ignored) {
                }
            }
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            if (fileCallback != null) {
                fileCallback.onReceiveValue(result);
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onDestroy() {
        cancelPageLoadTimeout();
        mainHandler.removeCallbacksAndMessages(null);
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {
            }
            networkCallback = null;
        }

        if (fileCallback != null) {
            fileCallback.onReceiveValue(null);
            fileCallback = null;
        }
        if (webView != null) {
            webView.stopLoading();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            webView.removeAllViews();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private String localeCode() {
        Locale locale = getResources().getConfiguration().getLocales().get(0);
        if (locale != null && "en".equalsIgnoreCase(locale.getLanguage())) {
            return "en";
        }
        return "ar";
    }

    private String appUrlWithLocale() {
        return APP_URL + "?app_lang=" + localeCode();
    }

    private String localizedInternalUrl(Uri uri) {
        if (uri == null) return appUrlWithLocale();
        Uri.Builder builder = uri.buildUpon().clearQuery();
        for (String name : uri.getQueryParameterNames()) {
            if ("app_lang".equals(name)) continue;
            for (String value : uri.getQueryParameters(name)) {
                builder.appendQueryParameter(name, value);
            }
        }
        builder.appendQueryParameter("app_lang", localeCode());
        return builder.build().toString();
    }

    private boolean isSystemDark() {
        int nightMode = getResources().getConfiguration().uiMode
            & Configuration.UI_MODE_NIGHT_MASK;
        return nightMode == Configuration.UI_MODE_NIGHT_YES;
    }

    private boolean isEnglishDevice() {
        Locale locale = getResources().getConfiguration().getLocales().get(0);
        return locale != null && "en".equalsIgnoreCase(locale.getLanguage());
    }

    private int surfaceColor() {
        return isSystemDark()
            ? Color.rgb(13, 16, 32)
            : Color.rgb(247, 248, 252);
    }

    private int primaryTextColor() {
        return isSystemDark()
            ? Color.rgb(243, 245, 251)
            : Color.rgb(15, 23, 42);
    }

    private int secondaryTextColor() {
        return isSystemDark()
            ? Color.rgb(154, 163, 188)
            : Color.rgb(100, 116, 139);
    }

    private void applySystemChrome() {
        boolean dark = isSystemDark();
        getWindow().setStatusBarColor(Color.rgb(17, 21, 42));
        getWindow().setNavigationBarColor(
            dark ? Color.rgb(13, 16, 32) : Color.rgb(247, 248, 252)
        );

        if (Build.VERSION.SDK_INT >= 26) {
            int flags = getWindow().getDecorView().getSystemUiVisibility();
            if (dark) {
                flags &= ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            } else {
                flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            }
            getWindow().getDecorView().setSystemUiVisibility(flags);
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
