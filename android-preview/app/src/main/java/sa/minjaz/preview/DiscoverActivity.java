package sa.minjaz.preview;

import android.app.Activity;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

/**
 * Native, public, read-only marketplace discovery. Never handles authentication,
 * sends cookies, submits orders or initiates payments. Every selected ID is
 * checked by the authenticated web workspace and again by the backend.
 */
public final class DiscoverActivity extends Activity {
    private static final int BACKGROUND = MinjazStyle.CANVAS;
    private static final int INK = MinjazStyle.INK;
    private static final int MUTED = MinjazStyle.MUTED;
    private static final int VIOLET = MinjazStyle.PURPLE;
    private static final long MAX_ID = 999999999999999L;
    private static final int MAX_RESPONSE_BYTES = 1500000;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final List<Category> categories = new ArrayList<>();
    private final List<Service> services = new ArrayList<>();
    private final Map<Long, String> categoryNames = new HashMap<>();

    private LinearLayout root;
    private LinearLayout filters;
    private LinearLayout results;
    private TextView status;
    private EditText search;
    private long selectedCategory = 0;
    private int visibleLimit = 40;
    private int loadGeneration = 0;

    private static final class Category {
        final long id;
        final String title;
        Category(long id, String title) { this.id = id; this.title = title; }
    }

    private static final class Service {
        final long id;
        final long categoryId;
        final String title;
        Service(long id, long categoryId, String title) {
            this.id = id; this.categoryId = categoryId; this.title = title;
        }
    }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(17, 21, 42));
        getWindow().setNavigationBarColor(BACKGROUND);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        createLayout();
        loadCatalog();
    }

    private void createLayout() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setBackgroundColor(BACKGROUND);
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars()
                        | WindowInsets.Type.displayCutout());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }
        setContentView(root);

        // Light first-party header mirrors the SwiftUI native brand.
        LinearLayout brandBar = new LinearLayout(this);
        brandBar.setGravity(Gravity.CENTER_VERTICAL);
        brandBar.setPadding(dp(18), dp(10), dp(18), dp(10));
        brandBar.setBackgroundColor(Color.WHITE);
        View mark = MinjazStyle.icon(this, MinjazStyle.MARK, VIOLET);
        brandBar.addView(mark, new LinearLayout.LayoutParams(dp(44), dp(44)));
        TextView brand = label(getString(R.string.app_name), 22, INK, true);
        LinearLayout.LayoutParams brandParams = new LinearLayout.LayoutParams(0, -2, 1);
        brandParams.setMargins(dp(8), 0, dp(8), 0);
        brandBar.addView(brand, brandParams);
        Button account = new Button(this);
        account.setText(R.string.nav_account);
        account.setAllCaps(false);
        account.setTextSize(12);
        account.setTextColor(VIOLET);
        account.setBackgroundTintList(ColorStateList.valueOf(MinjazStyle.PALE));
        account.setMinWidth(0);
        account.setMinHeight(0);
        account.setOnClickListener(v -> openNativeTab(4));
        brandBar.addView(account, new LinearLayout.LayoutParams(dp(76), dp(43)));
        root.addView(brandBar, new LinearLayout.LayoutParams(-1, dp(67)));

        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setPadding(dp(17), dp(18), dp(17), dp(19));
        hero.setBackground(MinjazStyle.surface(this, MinjazStyle.PALE, 20, false));
        TextView title = label(getString(R.string.discovery_title), 24, INK, true);
        title.setMaxLines(2);
        hero.addView(title);
        TextView sub = label(getString(R.string.discovery_subtitle), 14, MUTED, false);
        LinearLayout.LayoutParams subParams = new LinearLayout.LayoutParams(-1, -2);
        subParams.topMargin = dp(9);
        hero.addView(sub, subParams);
        LinearLayout.LayoutParams heroParams = new LinearLayout.LayoutParams(-1, -2);
        heroParams.setMargins(dp(16), dp(16), dp(16), dp(4));
        root.addView(hero, heroParams);

        LinearLayout searchPanel = new LinearLayout(this);
        searchPanel.setGravity(Gravity.CENTER_VERTICAL);
        searchPanel.setPadding(dp(12), 0, dp(12), 0);
        searchPanel.setBackground(MinjazStyle.surface(this, Color.WHITE, 17, true));
        View glass = MinjazStyle.icon(this, MinjazStyle.SEARCH, VIOLET);
        glass.setBackground(MinjazStyle.surface(this, MinjazStyle.PALE, 10, false));
        searchPanel.addView(glass, new LinearLayout.LayoutParams(dp(40), dp(40)));

        search = new EditText(this);
        search.setSingleLine(true);
        search.setTextSize(15);
        search.setTextColor(INK);
        search.setHint(R.string.discovery_search);
        search.setBackgroundColor(Color.TRANSPARENT);
        search.setPadding(dp(12), 0, dp(6), 0);
        MinjazStyle.text(search, false);
        searchPanel.addView(search, new LinearLayout.LayoutParams(0, -1, 1));
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(-1, dp(55));
        searchParams.setMargins(dp(16), dp(15), dp(16), dp(19));
        root.addView(searchPanel, searchParams);

        TextView filterHeading = label(getString(R.string.discovery_categories), 18, INK, true);
        filterHeading.setPadding(dp(18), 0, dp(18), dp(11));
        root.addView(filterHeading);

        HorizontalScrollView filterScroll = new HorizontalScrollView(this);
        filterScroll.setHorizontalScrollBarEnabled(false);
        filters = new LinearLayout(this);
        filters.setOrientation(LinearLayout.HORIZONTAL);
        filters.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        filters.setPadding(dp(12), 0, dp(12), 0);
        filterScroll.addView(filters);
        root.addView(filterScroll, new LinearLayout.LayoutParams(-1, dp(53)));

        status = label(getString(R.string.discovery_loading), 13, MUTED, false);
        status.setPadding(dp(18), dp(16), dp(18), dp(12));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(status);

        ScrollView scroll = new ScrollView(this);
        results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        results.setPadding(dp(16), dp(2), dp(16), dp(22));
        scroll.setFillViewport(true);
        scroll.addView(results);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        addNativeBottomNavigation();

        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                visibleLimit = 40;
                render();
            }
            @Override public void afterTextChanged(Editable s) {}
        });
    }

    private void addNativeBottomNavigation() {
        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setGravity(Gravity.CENTER);
        nav.setPadding(dp(4), dp(6), dp(4), dp(7));
        nav.setBackgroundColor(Color.WHITE);
        nav.setElevation(dp(7));
        int[] labels = {R.string.nav_discover, R.string.nav_projects, R.string.nav_orders,
            R.string.nav_services, R.string.nav_account};
        int[] icons = {MinjazStyle.GRID, MinjazStyle.BRIEFCASE, MinjazStyle.INBOX,
            MinjazStyle.SERVICES, MinjazStyle.USER};
        for (int i = 0; i < labels.length; i++) {
            final int tab = i;
            final boolean active = i == 0;
            LinearLayout item = new LinearLayout(this);
            item.setGravity(Gravity.CENTER);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setClickable(true);
            item.setFocusable(true);
            item.setContentDescription(getString(labels[i]));
            item.setSelected(active);
            item.setBackground(MinjazStyle.surface(this,
                active ? MinjazStyle.PALE : Color.WHITE, 14, false));
            item.setOnClickListener(v -> { if (!active) openNativeTab(tab); });

            View icon = MinjazStyle.icon(this, icons[i], active ? VIOLET : MUTED);
            item.addView(icon, new LinearLayout.LayoutParams(dp(28), dp(28)));
            TextView label = label(getString(labels[i]), 11, active ? VIOLET : MUTED, active);
            label.setGravity(Gravity.CENTER);
            label.setSingleLine(true);
            LinearLayout.LayoutParams labelParams = new LinearLayout.LayoutParams(-1, -2);
            labelParams.topMargin = dp(3);
            item.addView(label, labelParams);
            nav.addView(item, new LinearLayout.LayoutParams(0, -1, 1));
        }
        root.addView(nav, new LinearLayout.LayoutParams(-1, dp(70)));
    }

    private void openNativeTab(int tab) {
        if (tab == 0) return;
        if (tab == 3) {
            // Separate services filter reuses the first-party public catalog.
            // Never accidentally turn "Services" into an auth-gated project tab.
            selectedCategory = 0;
            search.setText("");
            renderFilters();
            render();
            return;
        }
        Intent intent = new Intent(this, NativeWorkspaceActivity.class);
        intent.putExtra("minjaz_tab", tab);
        startActivity(intent);
        finish();
    }

    private void loadCatalog() {
        final int generation = ++loadGeneration;
        status.setText(R.string.discovery_loading);
        results.removeAllViews();
        ProgressBar spinner = new ProgressBar(this);
        results.addView(spinner, new LinearLayout.LayoutParams(-1, dp(65)));

        executor.execute(() -> {
            try {
                JSONObject categoryResponse = readPublicApi("/api/v1/categories");
                JSONObject serviceResponse = readPublicApi("/api/v1/services");
                JSONArray parentRows = categoryResponse.getJSONArray("items");
                JSONArray serviceRows = serviceResponse.getJSONArray("items");

                List<Category> nextCategories = new ArrayList<>();
                List<Service> nextServices = new ArrayList<>();
                Map<Long, String> nextNames = new HashMap<>();
                for (int i = 0; i < parentRows.length() && i < 300; i++) {
                    JSONObject row = parentRows.getJSONObject(i);
                    long id = row.optLong("id", 0);
                    String title = row.optString("name_ar", "").trim();
                    if (validId(id) && !title.isEmpty() && title.length() <= 160
                        && !nextNames.containsKey(id)) {
                        nextNames.put(id, title);
                        nextCategories.add(new Category(id, title));
                    }
                }
                for (int i = 0; i < serviceRows.length() && i < 5000; i++) {
                    JSONObject row = serviceRows.getJSONObject(i);
                    long id = row.optLong("id", 0);
                    long categoryId = row.optLong("category_id", 0);
                    String title = row.optString("name_ar", "").trim();
                    if (validId(id) && nextNames.containsKey(categoryId)
                        && !title.isEmpty() && title.length() <= 160) {
                        nextServices.add(new Service(id, categoryId, title));
                    }
                }
                runOnUiThread(() -> {
                    if (!active(generation)) return;
                    categories.clear(); categories.addAll(nextCategories);
                    services.clear(); services.addAll(nextServices);
                    categoryNames.clear(); categoryNames.putAll(nextNames);
                    renderFilters();
                    render();
                });
            } catch (Exception exception) {
                runOnUiThread(() -> {
                    if (!active(generation)) return;
                    status.setText(R.string.discovery_connection_error);
                    results.removeAllViews();
                    Button retry = actionButton(getString(R.string.retry), () -> loadCatalog());
                    results.addView(retry);
                });
            }
        });
    }

    private JSONObject readPublicApi(String path) throws Exception {
        Uri base = Uri.parse(BuildConfig.APP_URL);
        if (!"https".equalsIgnoreCase(base.getScheme()) || base.getHost() == null
            || base.getUserInfo() != null || base.getPort() != -1 && base.getPort() != 443) {
            throw new SecurityException("Invalid first-party origin");
        }
        Uri endpoint = base.buildUpon().path(path).clearQuery().fragment(null).build();
        URL url = new URL(endpoint.toString());
        HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("Accept", "application/json");
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(18000);
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTP error");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] chunk = new byte[8192];
                int amount;
                while ((amount = input.read(chunk)) >= 0) {
                    if (bytes.size() + amount > MAX_RESPONSE_BYTES) {
                        throw new IllegalStateException("Oversized catalog response");
                    }
                    bytes.write(chunk, 0, amount);
                }
            }
            return new JSONObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
        } finally {
            connection.disconnect();
        }
    }

    private boolean active(int generation) {
        return generation == loadGeneration && !isFinishing() && !isDestroyed();
    }

    private static boolean validId(long id) {
        return id > 0 && id <= MAX_ID;
    }

    private void renderFilters() {
        filters.removeAllViews();
        addFilter(0, getString(R.string.discovery_all));
        for (Category category : categories) addFilter(category.id, category.title);
    }

    private void addFilter(long id, String title) {
        Button chip = new Button(this);
        chip.setText(title);
        chip.setAllCaps(false);
        chip.setTextSize(13);
        chip.setSingleLine(true);
        chip.setMinWidth(0);
        chip.setMinHeight(0);
        chip.setPadding(dp(17), 0, dp(17), 0);
        chip.setBackgroundTintList(ColorStateList.valueOf(
            selectedCategory == id ? VIOLET : Color.WHITE));
        chip.setTextColor(selectedCategory == id ? Color.WHITE : INK);
        chip.setOnClickListener(v -> {
            selectedCategory = id;
            visibleLimit = 40;
            renderFilters();
            render();
        });
        LinearLayout.LayoutParams chipParams = new LinearLayout.LayoutParams(-2, dp(44));
        chipParams.setMargins(dp(4), 0, dp(4), 0);
        filters.addView(chip, chipParams);
    }

    private void render() {
        if (services.isEmpty()) {
            if (!categories.isEmpty()) {
                status.setText(R.string.discovery_no_results);
                results.removeAllViews();
            }
            return;
        }
        String term = search.getText().toString().trim().toLowerCase(Locale.ROOT);
        List<Service> matched = new ArrayList<>();
        for (Service service : services) {
            if (selectedCategory != 0 && selectedCategory != service.categoryId) continue;
            String category = categoryNames.get(service.categoryId);
            if (term.isEmpty() || service.title.toLowerCase(Locale.ROOT).contains(term)
                || (category != null && category.toLowerCase(Locale.ROOT).contains(term))) {
                matched.add(service);
            }
        }
        status.setText(getString(R.string.discovery_count, matched.size()));
        results.removeAllViews();
        if (matched.isEmpty()) {
            results.addView(label(getString(R.string.discovery_no_results), 14, MUTED, false));
            return;
        }

        int displayed = Math.min(visibleLimit, matched.size());
        for (int i = 0; i < displayed; i++) {
            Service service = matched.get(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.HORIZONTAL);
            card.setGravity(Gravity.CENTER_VERTICAL);
            card.setPadding(dp(14), dp(13), dp(14), dp(13));
            card.setBackground(MinjazStyle.surface(this, Color.WHITE, 17, true));
            card.setElevation(dp(1));
            View icon = MinjazStyle.icon(this, MinjazStyle.BRIEFCASE, VIOLET);
            icon.setBackground(MinjazStyle.surface(this, MinjazStyle.PALE, 13, false));
            card.addView(icon, new LinearLayout.LayoutParams(dp(47), dp(47)));

            LinearLayout copy = new LinearLayout(this);
            copy.setOrientation(LinearLayout.VERTICAL);
            LinearLayout.LayoutParams copyParams = new LinearLayout.LayoutParams(0, -2, 1);
            copyParams.setMargins(dp(13), 0, dp(10), 0);
            card.addView(copy, copyParams);

            TextView name = label(service.title, 15, INK, true);
            name.setMaxLines(3);
            copy.addView(name);
            TextView category = label(categoryNames.get(service.categoryId), 12, MUTED, false);
            LinearLayout.LayoutParams catParams = new LinearLayout.LayoutParams(-1, -2);
            catParams.topMargin = dp(5);
            copy.addView(category, catParams);
            View chevron = MinjazStyle.icon(this, MinjazStyle.CHEVRON, MUTED);
            card.addView(chevron, new LinearLayout.LayoutParams(dp(22), dp(24)));
            card.setContentDescription(service.title + "، " + categoryNames.get(service.categoryId));
            card.setFocusable(true);
            card.setClickable(true);
            card.setOnClickListener(v -> openService(service));
            LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(-1, -2);
            cardParams.bottomMargin = dp(11);
            results.addView(card, cardParams);
        }
        if (matched.size() > displayed) {
            Button more = actionButton(getString(R.string.discovery_more), () -> {
                visibleLimit += 40;
                render();
            });
            results.addView(more);
        }
    }

    private void openService(Service service) {
        if (!validId(service.id) || !validId(service.categoryId)
            || !categoryNames.containsKey(service.categoryId)) return;
        Uri base = Uri.parse(BuildConfig.APP_URL);
        Uri destination = base.buildUpon()
            .path("/workspace").clearQuery()
            .appendQueryParameter("category_id", Long.toString(service.categoryId))
            .appendQueryParameter("service_id", Long.toString(service.id))
            .fragment("tasks-section").build();
        Intent intent = new Intent(this, MainActivity.class);
        intent.setAction(Intent.ACTION_VIEW);
        intent.setData(destination);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(intent);
        finish();
    }

    private Button actionButton(String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(14);
        button.setAllCaps(false);
        button.setTextColor(Color.WHITE);
        button.setBackgroundTintList(ColorStateList.valueOf(VIOLET));
        button.setOnClickListener(v -> action.run());
        return button;
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(radius));
        return shape;
    }

    private TextView label(String text, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.START);
        MinjazStyle.text(view, bold);
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override protected void onDestroy() {
        ++loadGeneration;
        executor.shutdownNow();
        super.onDestroy();
    }
}
