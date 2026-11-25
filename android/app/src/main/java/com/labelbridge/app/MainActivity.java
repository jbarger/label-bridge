package com.labelbridge.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.util.TypedValue;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;

/** Setup screen: pairing code, PC address (found automatically), test, and "choose PDFs". */
public class MainActivity extends Activity {
    static final String EXTRA_MESSAGE = "message";
    private static final int PICK_PDFS = 1;
    static final String PC_DOWNLOAD_URL = "https://github.com/jbarger/label-bridge/releases/latest";

    private Prefs prefs;
    private EditText code, host;
    private TextView status;
    private Button privacy;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = new Prefs(this);
        setTitle("Label Bridge");

        int pad = dp(20);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(pad, pad, pad, pad);

        col.addView(text("Print shipping labels from this phone on the 4x6 label printer connected to your PC.", 16));
        col.addView(text("\n1. On the PC, install Label Bridge for Windows (free):", 14));
        Button download = button("Get the PC app…");
        download.setOnClickListener(v -> open(PC_DOWNLOAD_URL));
        col.addView(download);

        col.addView(text("\n2. Type the pairing code shown in the PC app's settings:", 14));
        code = new EditText(this);
        code.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        code.setHint("e.g. W6XQYM");
        code.setText(prefs.code());
        col.addView(code);

        Button find = button("Find my PC on this Wi-Fi");
        find.setOnClickListener(v -> { save(); findPc(); });
        col.addView(find);

        col.addView(text("PC address (filled in automatically; type it only if Find doesn't work)", 13));
        host = new EditText(this);
        host.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        host.setHint("e.g. 192.168.0.20");
        host.setText(prefs.host());
        col.addView(host);

        Button test = button("Save and test connection");
        test.setOnClickListener(v -> saveAndTest());
        col.addView(test);

        status = text("", 15);
        status.setPadding(0, dp(8), 0, 0);
        col.addView(status);

        col.addView(text("\nEveryday use: in Gmail, Files, Drive or any app, tap Share on a label PDF "
                + "(or select several) and choose Label Bridge.", 14));
        Button pick = button("Choose PDFs to print…");
        pick.setOnClickListener(v -> {
            save();
            Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                    .addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("application/pdf")
                    .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            startActivityForResult(i, PICK_PDFS);
        });
        col.addView(pick);

        col.addView(text("\nPrint menu: turn on Label Bridge once in Android's printing settings. "
                + "Then in any app tap ⋮ → Print and choose the printer ending in \"(Label Bridge)\".", 14));
        Button printSettings = button("Turn on in the Print menu…");
        printSettings.setOnClickListener(v -> {
            try {
                startActivity(new Intent(android.provider.Settings.ACTION_PRINT_SETTINGS));
            } catch (Exception e) {
                status.setText("Open Settings and search for \"Printing\", then turn on Label Bridge.");
            }
        });
        col.addView(printSettings);

        privacy = button("Ad privacy choices");
        privacy.setVisibility(View.GONE);
        privacy.setOnClickListener(v -> Ads.showPrivacyOptions(this));
        col.addView(privacy);

        String msg = getIntent().getStringExtra(EXTRA_MESSAGE);
        if (msg != null) status.setText(msg);

        ScrollView sv = new ScrollView(this);
        sv.addView(col);

        // Banner sits below the scrolling content, never on top of the buttons.
        FrameLayout adSlot = new FrameLayout(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.addView(sv, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        root.addView(adSlot, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        applySystemBarInsets(root);
        setContentView(root);

        adSlot.post(() -> Ads.gatherConsentThenShow(this, adSlot,
                () -> privacy.setVisibility(Ads.privacyOptionsRequired(this) ? View.VISIBLE : View.GONE)));
    }

    /** Android 15+ draws apps edge to edge; keep content clear of the status and navigation bars. */
    private static void applySystemBarInsets(View root) {
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int l, t, r, b;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                l = i.left; t = i.top; r = i.right; b = i.bottom;
            } else {
                l = insets.getSystemWindowInsetLeft(); t = insets.getSystemWindowInsetTop();
                r = insets.getSystemWindowInsetRight(); b = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(l, t, r, b);
            return insets;
        });
    }

    private void open(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            status.setText("Open " + url + " on your PC.");
        }
    }

    private void save() {
        prefs.setCode(code.getText().toString());
        String h = host.getText().toString().trim();
        int port = Prefs.DEFAULT_PORT;
        int colon = h.lastIndexOf(':');
        if (colon > 0) {
            try { port = Integer.parseInt(h.substring(colon + 1)); h = h.substring(0, colon); }
            catch (NumberFormatException ignored) { }
        }
        prefs.setHost(h, port);
    }

    private void saveAndTest() {
        save();
        status.setText("Testing…");
        new Thread(() -> {
            PrintClient.Result r = new PrintClient(getApplicationContext()).ping();
            runOnUiThread(() -> {
                host.setText(prefs.host());
                status.setText((r.ok ? "✓ " : "✗ ") + r.detail);
            });
        }).start();
    }

    private void findPc() {
        status.setText("Looking for the PC…");
        new Thread(() -> {
            String[] found = Discovery.find(getApplicationContext(), 6000);
            runOnUiThread(() -> {
                if (found == null) {
                    status.setText("✗ Didn't find it. Make sure Label Bridge is running on the PC and this "
                            + "phone is on the same Wi-Fi, or type the PC's address.");
                } else {
                    prefs.setHost(found[0], Integer.parseInt(found[1]));
                    host.setText(found[0]);
                    saveAndTest();
                }
            });
        }).start();
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req != PICK_PDFS || res != RESULT_OK || data == null) return;
        ArrayList<Uri> uris = new ArrayList<>();
        if (data.getClipData() != null) {
            ClipData c = data.getClipData();
            for (int i = 0; i < c.getItemCount(); i++) uris.add(c.getItemAt(i).getUri());
        } else if (data.getData() != null) {
            uris.add(data.getData());
        }
        if (uris.isEmpty()) return;
        Intent send = new Intent(this, ShareActivity.class)
                .setAction(Intent.ACTION_SEND_MULTIPLE)
                .putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startActivity(send);
    }

    private TextView text(String s, int sp) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        return t;
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
