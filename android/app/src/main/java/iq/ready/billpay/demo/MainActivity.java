package iq.ready.billpay.demo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.http.SslError;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

/** Thin Android test client. Wallet, policy and provider secret remain on the server. */
public final class MainActivity extends Activity {
    private static final int NAVY = Color.rgb(21, 35, 63);
    private static final int MINT = Color.rgb(138, 226, 199);
    private static final int PURPLE = Color.rgb(101, 84, 192);
    private static final int PAPER = Color.rgb(245, 246, 251);
    private WebView webView;
    private ProgressBar progress;
    private ScrollView errorPanel;
    private TextView connectionLabel;
    private TextView errorHeading;
    private TextView errorDetail;
    private SharedPreferences preferences;
    private volatile String endpoint;
    private boolean pageFailed;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences("ready_endpoint", MODE_PRIVATE);
        try {
            endpoint = EndpointPolicy.normalize(preferences.getString("origin", EndpointPolicy.DEFAULT_ENDPOINT));
        } catch (IllegalArgumentException error) {
            endpoint = EndpointPolicy.DEFAULT_ENDPOINT;
        }
        buildLayout();
        configureWebView();
        loadBackend();
    }

    private void buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(NAVY);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(16), dp(8), dp(12), dp(8));
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        TextView name = label("READY  /  تجربة", 19, Color.WHITE);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        brand.addView(name);
        connectionLabel = label("جاري الاتصال", 11, MINT);
        connectionLabel.setMaxLines(1);
        brand.addView(connectionLabel);
        toolbar.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button settings = button("الاتصال", MINT, NAVY);
        settings.setContentDescription("إعداد عنوان خادم التجربة / Connection settings");
        settings.setOnClickListener(view -> showSettings());
        toolbar.addView(settings, new LinearLayout.LayoutParams(dp(96), dp(46)));
        root.addView(toolbar);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        FrameLayout content = new FrameLayout(this);
        content.setBackgroundColor(PAPER);
        webView = new WebView(this);
        webView.setBackgroundColor(PAPER);
        content.addView(webView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        errorPanel = new ScrollView(this);
        errorPanel.setFillViewport(true);
        errorPanel.setBackgroundColor(PAPER);
        LinearLayout errorContent = new LinearLayout(this);
        errorContent.setOrientation(LinearLayout.VERTICAL);
        errorContent.setGravity(Gravity.CENTER_VERTICAL);
        errorContent.setPadding(dp(26), dp(28), dp(26), dp(28));
        errorContent.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        TextView badge = label("نسخة اختبار • Topic 04", 13, PURPLE);
        badge.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        errorContent.addView(badge);
        errorHeading = label("خلّينا نربط التطبيق", 27, NAVY);
        errorHeading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        errorHeading.setPadding(0, dp(12), 0, dp(12));
        errorContent.addView(errorHeading);
        errorDetail = label("هذه النسخة تحتاج خادم التجربة على الكمبيوتر. المفتاح يبقى على الخادم، وكل الأموال والبيانات خيالية.", 16, NAVY);
        errorDetail.setLineSpacing(dp(4), 1);
        errorContent.addView(errorDetail);
        TextView steps = label("١. شغّل الخادم على الكمبيوتر.\n٢. وصّل الهاتف بـ USB وفعّل USB debugging.\n٣. شغّل أمر الربط ثم جرّب الاتصال.", 15, NAVY);
        steps.setPadding(0, dp(20), 0, dp(12));
        steps.setLineSpacing(dp(5), 1);
        errorContent.addView(steps);
        TextView commands = label("python server.py\n\nadb reverse tcp:8765 tcp:8765", 13, NAVY);
        commands.setTypeface(Typeface.MONOSPACE);
        commands.setTextDirection(View.TEXT_DIRECTION_LTR);
        commands.setTextIsSelectable(true);
        commands.setPadding(dp(14), dp(14), dp(14), dp(14));
        commands.setBackground(rounded(Color.WHITE, 12));
        errorContent.addView(commands);
        Button retry = button("إعادة المحاولة", PURPLE, Color.WHITE);
        retry.setOnClickListener(view -> loadBackend());
        LinearLayout.LayoutParams retryLayout = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54));
        retryLayout.topMargin = dp(20);
        errorContent.addView(retry, retryLayout);
        TextView reminder = label("التطبيق مستقل وليس تطبيق ZainCash الرسمي. فتح التطبيق وحده لا يشغّل الخادم أو نموذج الذكاء الاصطناعي.", 12, Color.rgb(92, 101, 119));
        reminder.setPadding(0, dp(18), 0, 0);
        reminder.setLineSpacing(dp(3), 1);
        errorContent.addView(reminder);
        errorPanel.addView(errorContent, new ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        content.addView(errorPanel, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        errorPanel.setVisibility(View.GONE);
        root.addView(content, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        TextView footer = label("بيانات خيالية فقط  •  لا أموال حقيقية", 11, MINT);
        footer.setGravity(Gravity.CENTER);
        footer.setPadding(dp(10), dp(7), dp(10), dp(7));
        root.addView(footer);
        setContentView(root);
        root.requestApplyInsets();
    }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSafeBrowsingEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) {
                progress.setProgress(value);
                progress.setVisibility(value == 100 ? View.GONE : View.VISIBLE);
            }
            @Override public void onPermissionRequest(PermissionRequest request) { request.deny(); }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return rejectNavigation(request.getUrl().toString());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return rejectNavigation(url);
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (EndpointPolicy.isSameOrigin(endpoint, request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked origin",
                        Collections.emptyMap(), new ByteArrayInputStream("Blocked origin".getBytes(StandardCharsets.UTF_8)));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!pageFailed && EndpointPolicy.isSameOrigin(endpoint, url)) {
                    connectionLabel.setText("خادم التجربة متصل");
                    errorPanel.setVisibility(View.GONE);
                    webView.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showConnectionError("ما قدرنا نتصل بالخادم", "تأكد من تشغيل الخادم وربط USB. ما انرسل أي طلب دفع من شاشة الاتصال.");
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) showConnectionError("الخادم رفض الاتصال", "راجع عنوان الخادم. النشر عبر HTTPS يحتاج إعداداً منفصلاً على الخادم؛ الربط المحلي بـ USB هو المسار الجاهز للاختبار.");
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showConnectionError("تعذّر التحقق من الاتصال الآمن", "شهادة HTTPS غير صالحة لهذا الاتصال. أصلح إعداد الخادم؛ التطبيق لا يتجاوز أخطاء الشهادة.");
            }
        });
    }

    private boolean rejectNavigation(String url) {
        if (EndpointPolicy.isSameOrigin(endpoint, url)) return false;
        Toast.makeText(this, "هذا الرابط خارج خادم التجربة المحدد.", Toast.LENGTH_SHORT).show();
        return true;
    }

    private void loadBackend() {
        pageFailed = false;
        errorPanel.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        connectionLabel.setText("جاري الاتصال بخادم التجربة");
        progress.setVisibility(View.VISIBLE);
        webView.loadUrl(endpoint);
    }

    private void showConnectionError(String heading, String detail) {
        pageFailed = true;
        connectionLabel.setText("الخادم غير متاح");
        errorHeading.setText(heading);
        errorDetail.setText(detail);
        progress.setVisibility(View.GONE);
        webView.setVisibility(View.GONE);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void showSettings() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(22), dp(12), dp(22), dp(4));
        TextView explanation = label("عنوان خادم التطبيق، مو رابط نموذج الذكاء الاصطناعي.\nلا تدخل API key هنا. المفتاح يتضبط على الكمبيوتر.\n\nالافتراضي للربط عبر USB:", 14, NAVY);
        explanation.setTextDirection(View.TEXT_DIRECTION_RTL);
        panel.addView(explanation);
        EditText address = new EditText(this);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setTextDirection(View.TEXT_DIRECTION_LTR);
        address.setSingleLine(true);
        address.setText(endpoint);
        address.setSelectAllOnFocus(true);
        address.setTextSize(14);
        panel.addView(address);
        TextView remote = label("HTTPS خيار متقدم لخادم نشرته وضبطته أنت. هذه النسخة ما تتضمن خادماً مستضافاً.", 12, Color.rgb(92, 101, 119));
        remote.setTextDirection(View.TEXT_DIRECTION_RTL);
        remote.setPadding(0, dp(8), 0, dp(8));
        panel.addView(remote);
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("اتصال READY")
                .setView(panel)
                .setNegativeButton("إلغاء", null)
                .setNeutralButton("الافتراضي", null)
                .setPositiveButton("حفظ واتصال", null)
                .create();
        dialog.setOnShowListener(ignored -> {
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(view -> address.setText(EndpointPolicy.DEFAULT_ENDPOINT));
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
                final String proposed;
                try { proposed = EndpointPolicy.normalize(address.getText().toString()); }
                catch (IllegalArgumentException error) {
                    address.setError("اكتب http://127.0.0.1:8765 أو عنوان HTTPS فقط، بدون مفتاح أو مسار.");
                    return;
                }
                if (!proposed.equals(endpoint) && proposed.startsWith("https://")) {
                    new AlertDialog.Builder(this).setTitle("تغيير خادم التجربة؟")
                            .setMessage("راح تتحمّل الواجهة من هذا الخادم. استخدم خادماً تملكه وتثق به. بيانات المحادثة تروح إلى هذا الخادم.\n\n" + proposed)
                            .setNegativeButton("إلغاء", null)
                            .setPositiveButton("اتصال", (confirmed, which) -> { dialog.dismiss(); changeEndpoint(proposed); })
                            .show();
                } else { dialog.dismiss(); changeEndpoint(proposed); }
            });
        });
        dialog.show();
    }

    private void changeEndpoint(String proposed) {
        if (proposed.equals(endpoint)) { loadBackend(); return; }
        webView.stopLoading();
        webView.clearHistory();
        webView.clearCache(true);
        WebStorage.getInstance().deleteAllData();
        CookieManager.getInstance().removeAllCookies(removed -> {
            CookieManager.getInstance().flush();
            endpoint = proposed;
            preferences.edit().putString("origin", endpoint).apply();
            loadBackend();
        });
    }

    @Override public void onBackPressed() {
        if (webView.canGoBack() && !pageFailed) webView.goBack();
        else super.onBackPressed();
    }

    @Override protected void onPause() { webView.onPause(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (webView != null) webView.onResume(); }
    @Override protected void onDestroy() {
        webView.stopLoading();
        webView.destroy();
        super.onDestroy();
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView label(String text, int size, int color) {
        TextView result = new TextView(this);
        result.setText(text); result.setTextSize(size); result.setTextColor(color);
        return result;
    }
    private Button button(String text, int background, int foreground) {
        Button result = new Button(this);
        result.setText(text); result.setAllCaps(false); result.setTextSize(14);
        result.setTextColor(foreground); result.setBackground(rounded(background, 12));
        result.setMinHeight(dp(48)); result.setPadding(dp(12), 0, dp(12), 0);
        return result;
    }
    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color); shape.setCornerRadius(dp(radius));
        return shape;
    }
}
