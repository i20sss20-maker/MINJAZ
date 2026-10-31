package sa.minjaz.preview;

import android.app.Activity;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.FrameLayout;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.HttpsURLConnection;

/**
 * Authenticated native marketplace surfaces. They fetch real first-party,
 * role-scoped resources using the WebView's verified-email session cookie.
 * Payment, offer submission, disputes and account deletion stay in the
 * established, authenticated workflow until native write contracts are tested.
 */
public final class NativeWorkspaceActivity extends Activity {
    private static final int INK = Color.rgb(17, 21, 42);
    private static final int PURPLE = Color.rgb(101, 88, 245);
    private static final int MUTED = Color.rgb(103, 111, 132);
    private static final int BACKGROUND = Color.rgb(247, 248, 252);
    private static final int MAX_BYTES = 1500000;
    private static final long MAX_ID = 999999999999999L;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private LinearLayout content;
    private LinearLayout[] tabs;
    private int selected = 1;
    private int requestGeneration = 0;
    private boolean isDestroyed = false;
    private String accountRole = "";
    private String accountName = "";
    private String accountEmail = "";

    private static final class SignInNeeded extends Exception {}
    private static final class UnexpectedResponse extends Exception {}

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(INK);
        getWindow().setNavigationBarColor(BACKGROUND);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        selected = getIntent().getIntExtra("minjaz_tab", 1);
        if (selected < 1 || selected > 6) selected = 1;
        createScreen();
    }

    @Override protected void onResume() {
        super.onResume();
        refresh();
    }

    @Override protected void onDestroy() {
        isDestroyed = true;
        requestGeneration++;
        executor.shutdownNow();
        super.onDestroy();
    }

    private void createScreen() {
        FrameLayout frame = new FrameLayout(this);
        frame.setBackgroundColor(BACKGROUND);
        frame.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);

        LinearLayout shell = new LinearLayout(this);
        shell.setOrientation(LinearLayout.VERTICAL);
        shell.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);

        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(dp(18), 0, dp(18), 0);
        top.setBackgroundColor(Color.WHITE);
        top.setElevation(dp(3));
        TextView brand = text(getString(R.string.app_name), 22, INK, true);
        top.addView(brand, new LinearLayout.LayoutParams(0, dp(60), 1));
        Button refresh = button(getString(R.string.native_refresh), false);
        refresh.setContentDescription(getString(R.string.native_refresh));
        refresh.setOnClickListener(v -> refresh());
        top.addView(refresh, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, dp(44)));
        shell.addView(top, new LinearLayout.LayoutParams(-1, dp(60)));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(18), dp(20), dp(18), dp(32));
        scroll.addView(content);
        shell.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER);
        bar.setPadding(dp(4), dp(7), dp(4), dp(8));
        bar.setBackgroundColor(Color.WHITE);
        bar.setElevation(dp(7));
        int[] labels = {R.string.nav_discover, R.string.nav_projects, R.string.nav_orders,
            R.string.nav_services, R.string.nav_account};
        String[] icons = {"⌕", "▤", "☷", "▦", "◉"};
        tabs = new LinearLayout[5];
        for (int i = 0; i < 5; i++) {
            final int tab = i;
            LinearLayout item = new LinearLayout(this);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setGravity(Gravity.CENTER);
            item.setClickable(true);
            item.setFocusable(true);
            item.setContentDescription(getString(labels[i]));
            item.setOnClickListener(v -> selectTab(tab));
            TextView icon = text(icons[i], 22, MUTED, false);
            icon.setGravity(Gravity.CENTER);
            item.addView(icon);
            TextView label = text(getString(labels[i]), 11, MUTED, false);
            label.setSingleLine(true);
            label.setGravity(Gravity.CENTER);
            item.addView(label);
            tabs[i] = item;
            bar.addView(item, new LinearLayout.LayoutParams(0, -1, 1));
        }
        shell.addView(bar, new LinearLayout.LayoutParams(-1, dp(70)));
        frame.addView(shell);
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            frame.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }
        setContentView(frame);
        updateTabs();
    }

    private void selectTab(int tab) {
        if (tab == 0 || tab == 3) {
            startActivity(new Intent(this, DiscoverActivity.class));
            return;
        }
        selected = tab;
        updateTabs();
        refresh();
    }

    private void updateTabs() {
        if (tabs == null) return;
        int chosen = selected >= 4 ? 4 : selected;
        for (int i = 0; i < tabs.length; i++) {
            boolean on = i == chosen;
            tabs[i].setSelected(on);
            tabs[i].setBackground(rounded(on ? Color.rgb(241, 239, 255) : Color.WHITE, 12));
            for (int j = 0; j < tabs[i].getChildCount(); j++) {
                if (tabs[i].getChildAt(j) instanceof TextView) {
                    TextView t = (TextView) tabs[i].getChildAt(j);
                    t.setTextColor(on ? PURPLE : MUTED);
                    t.setTypeface(null, on ? Typeface.BOLD : Typeface.NORMAL);
                }
            }
        }
    }

    private void refresh() {
        final int generation = ++requestGeneration;
        final int section = selected;
        content.removeAllViews();
        header(titleFor(section), getString(R.string.native_live_data));
        ProgressBar spinner = new ProgressBar(this);
        content.addView(spinner, new LinearLayout.LayoutParams(-1, dp(72)));

        executor.execute(() -> {
            try {
                JSONObject me = readFirstParty("/api/v1/me");
                JSONObject user = me.getJSONObject("user");
                String role = user.optString("role", "");
                String name = user.optString("name", "");
                String email = user.optString("email", "");
                JSONObject response = section == 4 ? null : readFirstParty(endpointFor(section));
                JSONArray items = response == null ? new JSONArray() : response.getJSONArray("items");
                runOnUiThread(() -> {
                    if (!validGeneration(generation)) return;
                    accountRole = role;
                    accountName = name;
                    accountEmail = email;
                    showData(section, items);
                });
            } catch (SignInNeeded e) {
                runOnUiThread(() -> {
                    if (!validGeneration(generation)) return;
                    content.removeAllViews();
                    header(titleFor(section), getString(R.string.native_signin_required));
                    empty(getString(R.string.native_signin_title),
                        getString(R.string.native_signin_required));
                    action(getString(R.string.account_login), () -> openWeb("/signup", "auth", "login", null));
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    if (!validGeneration(generation)) return;
                    content.removeAllViews();
                    header(titleFor(section), getString(R.string.native_load_failed));
                    empty(getString(R.string.native_load_failed), getString(R.string.native_retry_hint));
                    action(getString(R.string.retry), this::refresh);
                });
            }
        });
    }

    private boolean validGeneration(int generation) {
        return !isDestroyed && !isFinishing() && generation == requestGeneration;
    }

    private String endpointFor(int section) {
        switch (section) {
            case 1: return "/api/v1/tasks";
            case 2: return "/api/v1/orders";
            case 5: return "/api/v1/conversations";
            case 6: return "/api/v1/notifications";
            default: return "/api/v1/me";
        }
    }

    private String titleFor(int section) {
        switch (section) {
            case 1: return getString(R.string.native_projects);
            case 2: return getString(R.string.nav_orders);
            case 5: return getString(R.string.native_conversations);
            case 6: return getString(R.string.native_notifications);
            default: return getString(R.string.nav_account);
        }
    }

    private JSONObject readFirstParty(String path) throws Exception {
        if (!path.startsWith("/api/v1/")) throw new UnexpectedResponse();
        Uri base = Uri.parse(BuildConfig.APP_URL);
        if (!"https".equalsIgnoreCase(base.getScheme()) || base.getHost() == null
            || base.getUserInfo() != null || (base.getPort() != -1 && base.getPort() != 443)) {
            throw new UnexpectedResponse();
        }
        Uri target = base.buildUpon().path(path).clearQuery().fragment(null).build();
        if (!"https".equalsIgnoreCase(target.getScheme())
            || !base.getHost().equalsIgnoreCase(target.getHost())) {
            throw new UnexpectedResponse();
        }
        String cookie = CookieManager.getInstance().getCookie(BuildConfig.APP_URL);
        if (cookie == null || !cookie.matches("(?s)(^|.*;\\s*)minjaz_session=[^;]+.*")) {
            throw new SignInNeeded();
        }

        HttpsURLConnection connection = null;
        try {
            connection = (HttpsURLConnection) new URL(target.toString()).openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Cookie", cookie);
            connection.setUseCaches(false);
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(15000);
            int status = connection.getResponseCode();
            if (status == 401) throw new SignInNeeded();
            if (status != 200) throw new UnexpectedResponse();
            String type = connection.getContentType();
            if (type == null || !type.toLowerCase(java.util.Locale.ROOT).contains("application/json")) {
                throw new UnexpectedResponse();
            }
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream stream = connection.getInputStream()) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = stream.read(buffer)) != -1) {
                    if (bytes.size() + n > MAX_BYTES) throw new UnexpectedResponse();
                    bytes.write(buffer, 0, n);
                }
            }
            return new JSONObject(bytes.toString(StandardCharsets.UTF_8.name()));
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void showData(int section, JSONArray items) {
        content.removeAllViews();
        header(titleFor(section), getString(R.string.native_live_data));
        if (section == 4) {
            TextView name = text(accountName.isEmpty() ? getString(R.string.app_name) : accountName,
                22, INK, true);
            name.setPadding(dp(14), dp(18), dp(14), dp(4));
            content.addView(name);
            TextView email = text(accountEmail, 14, MUTED, false);
            email.setPadding(dp(14), 0, dp(14), dp(18));
            content.addView(email);
            action(getString(R.string.native_conversations), () -> switchInnerSection(5));
            action(getString(R.string.native_notifications), () -> switchInnerSection(6));
            action(getString(R.string.account_profile), () -> openWeb("/workspace", null, null, "profile"));
            action(getString(R.string.account_privacy), () -> openWeb("/privacy", null, null, null));
            action(getString(R.string.account_deletion), () -> openWeb("/account-deletion", null, null, null));
            action(getString(R.string.account_login), () -> openWeb("/signup", "auth", "login", null));
            return;
        }
        if (section == 1 && "client".equals(accountRole)) {
            action(getString(R.string.native_publish), () -> openWeb("/workspace", null, null, "tasks-section"));
        }
        if (items.length() == 0) {
            empty(getString(R.string.native_empty_title), getString(R.string.native_empty_desc));
            return;
        }
        TextView counter = text(items.length() + " " + getString(R.string.native_results), 12, MUTED, true);
        counter.setPadding(dp(3), dp(8), 0, dp(13));
        content.addView(counter);
        for (int i = 0; i < items.length() && i < 100; i++) {
            JSONObject row = items.optJSONObject(i);
            if (row == null) continue;
            String idKey = section == 5 ? "order_id" : "id";
            long id = row.optLong(idKey, 0);
            if (id <= 0 || id > MAX_ID) continue;
            String title = row.optString("title", "").trim();
            if (title.isEmpty()) continue;
            String description;
            if (section == 1) description = row.optString("service_name",
                row.optString("category_name", ""));
            else if (section == 2) description = "freelancer".equals(accountRole)
                ? row.optString("client_name", "") : row.optString("freelancer_name", "");
            else if (section == 5) description = row.optString("counterpart_name", "") + " · "
                + row.optString("last_message", "");
            else description = row.optString("body", "");
            String status = section == 6 ? row.optString("kind", "") : row.optString("status", "");
            String amount = section == 2 ? row.optString("amount", "") : "";
            boolean unread = (section == 5 && row.optInt("unread_messages", 0) > 0)
                || (section == 6 && row.isNull("read_at"));
            record(title, description, status, amount, unread, () ->
                openWeb("/workspace", null, null,
                    section == 1 ? "tasks-section"
                    : section == 2 ? "orders-section"
                    : section == 5 ? "messages-section" : "notifications-section"));
        }
    }

    private void switchInnerSection(int section) {
        selected = section;
        updateTabs();
        refresh();
    }

    private void header(String title, String subtitle) {
        TextView h = text(title, 26, INK, true);
        h.setPadding(0, 0, 0, dp(6));
        content.addView(h);
        TextView p = text(subtitle, 13, MUTED, false);
        p.setPadding(0, 0, 0, dp(18));
        content.addView(p);
    }

    private void empty(String title, String hint) {
        LinearLayout card = card();
        TextView t = text(title, 18, INK, true);
        t.setGravity(Gravity.CENTER);
        card.addView(t);
        TextView p = text(hint, 13, MUTED, false);
        p.setGravity(Gravity.CENTER);
        p.setPadding(dp(10), dp(10), dp(10), 0);
        card.addView(p);
        addCard(card);
    }

    private void record(String title, String subtitle, String status, String amount,
                        boolean unread, Runnable open) {
        LinearLayout card = card();
        if (unread) {
            TextView flag = text(getString(R.string.native_unread), 11, PURPLE, true);
            card.addView(flag);
        }
        TextView t = text(title, 16, INK, true);
        t.setMaxLines(2);
        card.addView(t);
        if (!subtitle.isEmpty()) {
            TextView d = text(subtitle, 13, MUTED, false);
            d.setMaxLines(3);
            d.setPadding(0, dp(7), 0, dp(5));
            card.addView(d);
        }
        LinearLayout bottom = new LinearLayout(this);
        bottom.setGravity(Gravity.CENTER_VERTICAL);
        TextView state = text(status, 12, PURPLE, false);
        bottom.addView(state, new LinearLayout.LayoutParams(0, dp(28), 1));
        if (!amount.isEmpty() && !"null".equals(amount)) {
            bottom.addView(text(amount + " ر.س", 13, INK, true));
        }
        card.addView(bottom);
        card.setClickable(true);
        card.setFocusable(true);
        card.setContentDescription(title);
        card.setOnClickListener(v -> open.run());
        addCard(card);
    }

    private void action(String label, Runnable click) {
        Button btn = button(label, true);
        btn.setOnClickListener(v -> click.run());
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(50));
        params.bottomMargin = dp(12);
        content.addView(btn, params);
    }

    private void openWeb(String path, String key, String value, String fragment) {
        Uri base = Uri.parse(BuildConfig.APP_URL);
        Uri.Builder builder = base.buildUpon().path(path).clearQuery().fragment(fragment);
        if (key != null && value != null) builder.appendQueryParameter(key, value);
        Uri target = builder.build();
        if (!"https".equalsIgnoreCase(target.getScheme()) ||
            !base.getHost().equalsIgnoreCase(target.getHost()) ||
            (target.getPort() != -1 && target.getPort() != 443) ||
            target.getUserInfo() != null) return;
        Intent intent = new Intent(this, MainActivity.class);
        intent.setData(target);
        startActivity(intent);
    }

    private LinearLayout card() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(17), dp(16), dp(17), dp(16));
        box.setBackground(rounded(Color.WHITE, 16));
        return box;
    }

    private void addCard(LinearLayout box) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.bottomMargin = dp(12);
        content.addView(box, p);
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        return drawable;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(null, Typeface.BOLD);
        return view;
    }

    private Button button(String title, boolean emphasized) {
        Button view = new Button(this);
        view.setText(title);
        view.setAllCaps(false);
        view.setTextSize(13);
        view.setMinWidth(0);
        view.setMinHeight(0);
        view.setTextColor(emphasized ? Color.WHITE : PURPLE);
        view.setBackgroundTintList(ColorStateList.valueOf(
            emphasized ? PURPLE : Color.rgb(241, 239, 255)));
        return view;
    }

    private int dp(int value) {
        return (int) (getResources().getDisplayMetrics().density * value + 0.5f);
    }
}
