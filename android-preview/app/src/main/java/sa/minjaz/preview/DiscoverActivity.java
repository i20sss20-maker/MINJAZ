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
    private static final int BACKGROUND = Color.rgb(247, 248, 252);
    private static final int INK = Color.rgb(21, 26, 49);
    private static final int MUTED = Color.rgb(105, 112, 134);
    private static final int VIOLET = Color.rgb(74, 53, 167);
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

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(18), dp(14), dp(18), dp(16));
        header.setBackgroundColor(Color.rgb(20, 20, 49));

        Button back = new Button(this);
        back.setText(R.string.discovery_back);
        back.setAllCaps(false);
        back.setTextColor(Color.WHITE);
        back.setTextSize(13);
        back.setBackgroundTintList(ColorStateList.valueOf(Color.rgb(52, 48, 90)));
        back.setOnClickListener(v -> finish());
        header.addView(back, new LinearLayout.LayoutParams(dp(115), dp(45)));

        TextView title = label(getString(R.string.discovery_title), 25, Color.WHITE, true);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        titleParams.topMargin = dp(8);
        header.addView(title, titleParams);
        TextView sub = label(getString(R.string.discovery_subtitle), 13,
            Color.rgb(211, 210, 235), false);
        LinearLayout.LayoutParams subParams = new LinearLayout.LayoutParams(-1, -2);
        subParams.topMargin = dp(8);
        header.addView(sub, subParams);
        root.addView(header);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setTextSize(15);
        search.setTextColor(INK);
        search.setHint(R.string.discovery_search);
        search.setPadding(dp(14), dp(10), dp(14), dp(10));
        search.setBackground(rounded(Color.WHITE, 16));
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(-1, dp(52));
        searchParams.setMargins(dp(16), dp(16), dp(16), dp(12));
        root.addView(search, searchParams);

        HorizontalScrollView filterScroll = new HorizontalScrollView(this);
        filterScroll.setHorizontalScrollBarEnabled(false);
        filters = new LinearLayout(this);
        filters.setOrientation(LinearLayout.HORIZONTAL);
        filters.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        filters.setPadding(dp(12), 0, dp(12), 0);
        filterScroll.addView(filters);
        root.addView(filterScroll, new LinearLayout.LayoutParams(-1, dp(54)));

        status = label(getString(R.string.discovery_loading), 12, MUTED, false);
        status.setPadding(dp(18), dp(10), dp(18), dp(8));
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        root.addView(status);

        ScrollView scroll = new ScrollView(this);
        results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        results.setPadding(dp(16), dp(2), dp(16), dp(20));
        scroll.setFillViewport(true);
        scroll.addView(results);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                visibleLimit = 40;
                render();
            }
            @Override public void afterTextChanged(Editable s) {}
        });
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
        chip.setTextSize(12);
        chip.setMinHeight(dp(40));
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
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(dp(16), dp(14), dp(16), dp(14));
            card.setBackground(rounded(Color.WHITE, 15));
            TextView name = label(service.title, 16, INK, true);
            card.addView(name);
            TextView category = label(categoryNames.get(service.categoryId), 12, MUTED, false);
            LinearLayout.LayoutParams catParams = new LinearLayout.LayoutParams(-1, -2);
            catParams.topMargin = dp(6);
            card.addView(category, catParams);
            card.setContentDescription(service.title + "، " + categoryNames.get(service.categoryId));
            card.setFocusable(true);
            card.setClickable(true);
            card.setOnClickListener(v -> openService(service));
            LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(-1, -2);
            cardParams.bottomMargin = dp(10);
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
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
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
