package sa.minjaz.preview;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
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
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.URLUtil;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Locale;

public class MainActivity extends Activity {
    // Distribution-specific HTTPS origin. Preview can NEVER silently use production.
    private static final String APP_URL = BuildConfig.APP_URL;
    private static final String APP_HOST = Uri.parse(APP_URL).getHost();
    private static final int FILE_CHOOSER_REQUEST = 7001;
    private static final long PAGE_LOAD_TIMEOUT_MS = 20000L;
    private static final long BACK_HANDLER_TIMEOUT_MS = 1500L;

    private FrameLayout root;
    private WebView webView;
    private LinearLayout bottomNav;
    private TextView[] navIcons;
    private TextView[] navLabels;
    private LinearLayout[] navItems;
    private int activeTab = 1;
    private View loadingView;
    private View errorView;
    private ValueCallback<Uri[]> fileCallback;
    private ConnectivityManager connectivityManager;
    private ConnectivityManager.NetworkCallback networkCallback;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private Runnable pageLoadTimeout;
    private Runnable pendingNetworkRetry;
    private int pageLoadGeneration = 0;
    private String lastGoodUrl;
    private boolean backHandling = false;
    private Runnable backHandlingTimeout;
    private int backHandlingGeneration = 0;

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
        webView.setLayoutParams(browserContentParams());
        root.addView(webView);

        loadingView = buildLoadingView();
        root.addView(loadingView, browserContentParams());

        errorView = buildErrorView();
        errorView.setVisibility(View.GONE);
        root.addView(errorView, browserContentParams());

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

        // Native controls sit above the WebView and its network overlays,
        // while the content has its own reserved bounds. No floating CTA
        // can cover a marketplace form field or the Android keyboard.
        buildNativeHeaderAndNavigation();
        setContentView(root);
    }

    private FrameLayout.LayoutParams browserContentParams() {
        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        );
        p.topMargin = dp(58);
        p.bottomMargin = dp(70);
        return p;
    }

    private GradientDrawable panelBackground(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        return drawable;
    }

    private void buildNativeHeaderAndNavigation() {
        final int dark = Color.rgb(17, 21, 42);
        final int accent = Color.rgb(101, 88, 245);
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setPadding(dp(16), 0, dp(16), 0);
        header.setBackgroundColor(Color.WHITE);
        header.setElevation(dp(3));

        TextView brand = new TextView(this);
        brand.setText(getString(R.string.app_name));
        brand.setTextSize(21);
        brand.setTextColor(dark);
        brand.setTypeface(null, android.graphics.Typeface.BOLD);
        header.addView(brand, new LinearLayout.LayoutParams(0, dp(58), 1));

        Button account = new Button(this);
        account.setText(R.string.account_menu_title);
        account.setTextSize(12);
        account.setAllCaps(false);
        account.setTextColor(accent);
        account.setMinHeight(0);
        account.setMinWidth(0);
        account.setBackgroundTintList(android.content.res.ColorStateList.valueOf(
            Color.rgb(243, 240, 255)));
        account.setOnClickListener(v -> showAccountMenu());
        header.addView(account, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, dp(44)));
        FrameLayout.LayoutParams headerParams = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(58), Gravity.TOP);
        root.addView(header, headerParams);

        bottomNav = new LinearLayout(this);
        bottomNav.setOrientation(LinearLayout.HORIZONTAL);
        bottomNav.setGravity(Gravity.CENTER);
        bottomNav.setPadding(dp(3), dp(5), dp(3), dp(4));
        bottomNav.setBackgroundColor(Color.WHITE);
        bottomNav.setElevation(dp(8));
        int[] labels = {R.string.nav_discover, R.string.nav_projects, R.string.nav_orders,
            R.string.nav_services, R.string.nav_account};
        String[] glyphs = {"⌕", "▤", "☷", "▦", "◉"};
        navItems = new LinearLayout[labels.length];
        navIcons = new TextView[labels.length];
        navLabels = new TextView[labels.length];
        for (int i = 0; i < labels.length; i++) {
            final int tab = i;
            LinearLayout item = new LinearLayout(this);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setGravity(Gravity.CENTER);
            item.setClickable(true);
            item.setFocusable(true);
            item.setContentDescription(getString(labels[i]));
            item.setOnClickListener(v -> navigateNativeTab(tab));

            TextView icon = new TextView(this);
            icon.setText(glyphs[i]);
            icon.setTextSize(23);
            icon.setGravity(Gravity.CENTER);
            item.addView(icon, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(32)));

            TextView label = new TextView(this);
            label.setText(labels[i]);
            label.setTextSize(11);
            label.setSingleLine(true);
            label.setGravity(Gravity.CENTER);
            item.addView(label, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(21)));
            navItems[i] = item;
            navIcons[i] = icon;
            navLabels[i] = label;
            bottomNav.addView(item, new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.MATCH_PARENT, 1));
        }
        FrameLayout.LayoutParams bottomParams = new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(70), Gravity.BOTTOM);
        root.addView(bottomNav, bottomParams);
        highlightTab(activeTab);
    }

    private void highlightTab(int tab) {
        if (navItems == null || tab < 0 || tab >= navItems.length) return;
        activeTab = tab;
        int accent = Color.rgb(101, 88, 245);
        int muted = Color.rgb(107, 118, 140);
        for (int i = 0; i < navItems.length; i++) {
            boolean selected = i == tab;
            navItems[i].setSelected(selected);
            navIcons[i].setTextColor(selected ? accent : muted);
            navLabels[i].setTextColor(selected ? accent : muted);
            navLabels[i].setTypeface(null, selected
                ? android.graphics.Typeface.BOLD : android.graphics.Typeface.NORMAL);
            navItems[i].setBackground(selected
                ? panelBackground(Color.rgb(246, 244, 255), 13)
                : panelBackground(Color.WHITE, 13));
        }
    }

    private void navigateNativeTab(int tab) {
        if (tab == 0) {
            startActivity(new Intent(MainActivity.this, DiscoverActivity.class));
            return;
        }
        if (tab == 4) {
            openInternalAccountPage("/workspace", null, null, "profile");
        } else if (tab == 3) {
            openInternalAccountPage("/digital-services", null, null);
        } else if (tab == 2) {
            openInternalAccountPage("/workspace", null, null, "orders-section");
        } else if (tab == 1) {
            openInternalAccountPage("/workspace", null, null, "tasks-section");
        }
        highlightTab(tab);
    }

    private void syncSelectedTab(String url) {
        if (!safeInternalUrl(url)) return;
        Uri uri = Uri.parse(url);
        String path = uri.getPath();
        if ("/digital-services".equals(path)) highlightTab(3);
        else if ("/account-deletion".equals(path) || "/privacy".equals(path)
                || "/signup".equals(path)) highlightTab(4);
        else if ("/workspace".equals(path)) {
            String fragment = uri.getFragment();
            if ("profile".equals(fragment)) highlightTab(4);
            else if ("orders-section".equals(fragment)) highlightTab(2);
            else highlightTab(1);
        }
    }

    private void showAccountMenu() {
        String[] actions = {
            getString(R.string.account_login),
            getString(R.string.account_profile),
            getString(R.string.account_privacy),
            getString(R.string.account_deletion)
        };
        new AlertDialog.Builder(this)
            .setTitle(R.string.account_menu_title)
            .setItems(actions, (dialog, selection) -> {
                switch (selection) {
                    case 0: openInternalAccountPage("/signup", "auth", "login"); break;
                    case 1: openInternalAccountPage("/workspace", null, null); break;
                    case 2: openInternalAccountPage("/privacy", null, null); break;
                    case 3: openInternalAccountPage("/account-deletion", null, null); break;
                    default: break;
                }
            })
            .setNegativeButton(android.R.string.cancel, null)
            .show();
    }

    private void openInternalAccountPage(String path, String queryKey, String queryValue) {
        if (webView == null) return;
        openInternalAccountPage(path, queryKey, queryValue, null);
    }

    private void openInternalAccountPage(
        String path, String queryKey, String queryValue, String fragment
    ) {
        Uri.Builder builder = Uri.parse(APP_URL).buildUpon()
            .path(path).clearQuery().fragment(fragment);
        if (queryKey != null && queryValue != null) {
            builder.appendQueryParameter(queryKey, queryValue);
        }
        Uri target = builder.build();
        if (!isInternalUri(target)) return;
        webView.loadUrl(localizedInternalUrl(target));
        syncSelectedTab(target.toString());
    }

    private View buildLoadingView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(dp(28), dp(28), dp(28), dp(28));
        box.setBackgroundColor(surfaceColor());

        TextView brand = new TextView(this);
        brand.setText(getString(R.string.app_name));
        brand.setTextSize(24);
        brand.setTextColor(primaryTextColor());
        brand.setGravity(Gravity.CENTER);
        box.addView(brand);

        ProgressBar progress = new ProgressBar(this);
        progress.setIndeterminate(true);
        LinearLayout.LayoutParams progressParams = new LinearLayout.LayoutParams(
            dp(42),
            dp(42)
        );
        progressParams.topMargin = dp(18);
        box.addView(progress, progressParams);

        TextView message = new TextView(this);
        message.setText(getString(R.string.loading));
        message.setTextSize(13);
        message.setTextColor(secondaryTextColor());
        message.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams messageParams = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
        messageParams.topMargin = dp(14);
        box.addView(message, messageParams);

        return box;
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

        // MINJAZ controls its own appearance. Never let Android/WebView force
        // dark mode just because the device is using a dark system theme.
        if (Build.VERSION.SDK_INT >= 33) {
            settings.setAlgorithmicDarkeningAllowed(false);
        } else if (Build.VERSION.SDK_INT >= 29) {
            settings.setForceDark(WebSettings.FORCE_DARK_OFF);
        }

        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setUserAgentString(settings.getUserAgentString() + " MINJAZ-Android/" + BuildConfig.VERSION_NAME);

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
                finishFileChooser(null);
                fileCallback = callback;
                try {
                    // createIntent can fail if the device has no file picker.
                    Intent intent = params.createIntent();
                    if (intent == null) throw new ActivityNotFoundException();
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception e) {
                    finishFileChooser(null);
                    Toast.makeText(MainActivity.this, R.string.file_picker_unavailable, Toast.LENGTH_LONG).show();
                    return true;
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
        return "https".equals(scheme) && APP_HOST.equalsIgnoreCase(host)
            && (uri.getPort() == -1 || uri.getPort() == 443)
            && uri.getUserInfo() == null;
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

    private boolean safeExternalUri(Uri uri) {
        if (uri == null) return false;
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if ("https".equals(scheme) || "http".equals(scheme)) {
            return uri.getHost() != null && !uri.getHost().isEmpty();
        }
        // Do not hand javascript:, file:, content:, data: or blob: to ACTION_VIEW.
        return "mailto".equals(scheme) || "tel".equals(scheme)
            || "sms".equals(scheme) || "smsto".equals(scheme)
            || "market".equals(scheme) || "geo".equals(scheme);
    }

    private void openExternal(Uri uri) {
        if (!safeExternalUri(uri)) return;
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
            if (view != webView) return;
            super.onPageStarted(view, url, favicon);
            if (url != null && isInternalUri(Uri.parse(url))) {
                hideError();
                showLoading();
                schedulePageLoadTimeout(url);
            } else {
                hideLoading();
                cancelPageLoadTimeout();
            }
        }

        @Override
        public void onPageCommitVisible(WebView view, String url) {
            if (view != webView) return;
            cancelPageLoadTimeout();
            if (url != null) {
                try {
                    Uri uri = Uri.parse(url);
                    if (isInternalUri(uri)) {
                        lastGoodUrl = localizedInternalUrl(uri);
                        syncSelectedTab(url);
                    }
                } catch (Exception ignored) {
                }
            }
            hideError();
            hideLoading();
            super.onPageCommitVisible(view, url);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (view != webView) return;
            cancelPageLoadTimeout();
            hideLoading();
            super.onPageFinished(view, url);
        }

        @Override
        public void onReceivedError(
            WebView view,
            WebResourceRequest request,
            WebResourceError error
        ) {
            if (view != webView) return;
            if (request.isForMainFrame()) {
                cancelPageLoadTimeout();
                hideLoading();
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
            if (view != webView) return;
            if (request.isForMainFrame() && errorResponse.getStatusCode() >= 400) {
                cancelPageLoadTimeout();
                hideLoading();
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
            if (view == webView) recoverWebView();
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
                // A network can be available before it has usable internet.
                runOnUiThread(MainActivity.this::scheduleNetworkRetry);
            }

            @Override
            public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities) {
                if (capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
                    runOnUiThread(MainActivity.this::scheduleNetworkRetry);
                }
            }
        };

        try {
            connectivityManager.registerDefaultNetworkCallback(networkCallback);
        } catch (Exception ignored) {
            networkCallback = null;
        }
    }

    private void scheduleNetworkRetry() {
        // Coalesce Wi-Fi/mobile hand-offs into one validated retry.
        if (pendingNetworkRetry != null) mainHandler.removeCallbacks(pendingNetworkRetry);
        pendingNetworkRetry = () -> {
            pendingNetworkRetry = null;
            if (webView != null && errorView != null
                && errorView.getVisibility() == View.VISIBLE && isNetworkReady()) {
                retryCurrentPage();
            }
        };
        mainHandler.postDelayed(pendingNetworkRetry, 650);
    }

    private void recoverWebView() {
        cancelBackHandling();
        cancelPageLoadTimeout();
        // The old renderer owns the file input: close its callback before replacement.
        finishFileChooser(null);
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
        webView.setLayoutParams(browserContentParams());
        root.addView(webView, 0);
        configureWebView();
        hideError();
        showLoading();
        webView.loadUrl(lastUrl);
    }

    private void showLoading() {
        if (loadingView != null) loadingView.setVisibility(View.VISIBLE);
    }

    private void hideLoading() {
        if (loadingView != null) loadingView.setVisibility(View.GONE);
    }

    private void showError() {
        hideLoading();
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
        showLoading();
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
                hideLoading();
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

    private void cancelBackHandling() {
        backHandlingGeneration++;
        backHandling = false;
        if (backHandlingTimeout != null) {
            mainHandler.removeCallbacks(backHandlingTimeout);
            backHandlingTimeout = null;
        }
    }

    private void completeBackHandling(int generation, boolean handled) {
        // Ignore late callbacks from a dead renderer or a superseded back press.
        if (!backHandling || generation != backHandlingGeneration) return;
        cancelBackHandling();
        if (!handled) nativeBackFallback();
    }

    private void handleBack() {
        if (backHandling) return;
        if (errorView != null && errorView.getVisibility() == View.VISIBLE) {
            hideError();
            // Do not expose the underlying WebView error page.
            nativeBackFallback();
            return;
        }
        if (webView == null) {
            finish();
            return;
        }
        backHandling = true;
        final int generation = ++backHandlingGeneration;
        backHandlingTimeout = () -> completeBackHandling(generation, false);
        mainHandler.postDelayed(backHandlingTimeout, BACK_HANDLER_TIMEOUT_MS);
        String script = "(function(){try{"
            + "var g=document.getElementById('globalSearchOverlayV28');"
            + "if(g&&g.classList.contains('on')&&window.closeGlobalSearchV28){window.closeGlobalSearchV28();return true;}"
            + "var o=document.getElementById('modalOverlay');"
            + "if(o&&o.classList.contains('on')&&window.closeModal){window.closeModal();return true;}"
            + "var p=document.querySelector('.page.on');"
            + "if(p&&p.id&&p.id!=='home'&&window.go){window.go('home');return true;}"
            + "return false;}catch(e){return false;}})();";
        try {
            webView.evaluateJavascript(
                script, value -> completeBackHandling(generation, "true".equals(value))
            );
        } catch (RuntimeException ignored) {
            completeBackHandling(generation, false);
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        cancelBackHandling();
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
                scheduleNetworkRetry();
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
        cancelBackHandling();
        if (webView != null) webView.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    private void finishFileChooser(Uri[] uris) {
        ValueCallback<Uri[]> pending = fileCallback;
        fileCallback = null;
        if (pending != null) pending.onReceiveValue(uris);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            finishFileChooser(result);
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onDestroy() {
        cancelBackHandling();
        cancelPageLoadTimeout();
        if (pendingNetworkRetry != null) {
            mainHandler.removeCallbacks(pendingNetworkRetry);
            pendingNetworkRetry = null;
        }
        mainHandler.removeCallbacksAndMessages(null);
        if (connectivityManager != null && networkCallback != null) {
            try {
                connectivityManager.unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {
            }
            networkCallback = null;
        }

        finishFileChooser(null);
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
        // Light is the product default. Dark mode is an explicit in-app choice,
        // not something Android should impose from the device theme.
        return false;
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
