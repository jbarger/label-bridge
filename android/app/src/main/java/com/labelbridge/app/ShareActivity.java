package com.labelbridge.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

/** Receives one or many PDFs from the Share sheet / "Open with" and sends each to the PC in turn. */
public class ShareActivity extends Activity {

    private TextView log;
    private ProgressBar spinner;
    private Button close;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        setTitle("Label Bridge");
        buildUi();

        if (!new Prefs(this).isPaired()) {
            startActivity(new Intent(this, MainActivity.class)
                    .putExtra(MainActivity.EXTRA_MESSAGE, "Enter the pairing code first, then share the label again."));
            finish();
            return;
        }

        final List<Uri> uris = collectUris(getIntent());
        if (uris.isEmpty()) {
            done("No PDF was shared.", false);
            return;
        }
        final PrintClient client = new PrintClient(getApplicationContext());
        new Thread(() -> {
            int ok = 0;
            for (int i = 0; i < uris.size(); i++) {
                Uri u = uris.get(i);
                String name = client.displayName(u);
                String prefix = uris.size() > 1 ? (i + 1) + "/" + uris.size() + "  " : "";
                append(prefix + name + " …");
                PrintClient.Result r = client.print(u);
                if (r.ok) ok++;
                String mark = "printed".equals(r.status) ? "✓ printed"
                        : "queued".equals(r.status) ? "✓ sent (printing)" : "✗ " + r.detail;
                append("    " + mark);
            }
            final int good = ok;
            ui.post(() -> done(good == uris.size()
                    ? (uris.size() == 1 ? "Done." : "All " + good + " labels sent.")
                    : (uris.size() - good) + " of " + uris.size() + " didn't print.", good == uris.size()));
        }, "send-labels").start();
    }

    static List<Uri> collectUris(Intent in) {
        LinkedHashSet<Uri> set = new LinkedHashSet<>();
        if (in == null) return new ArrayList<>(set);
        if (Intent.ACTION_SEND_MULTIPLE.equals(in.getAction())) {
            ArrayList<Uri> list = in.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (list != null) set.addAll(list);
        } else if (Intent.ACTION_SEND.equals(in.getAction())) {
            Uri u = in.getParcelableExtra(Intent.EXTRA_STREAM);
            if (u != null) set.add(u);
        } else if (in.getData() != null) {
            set.add(in.getData());
        }
        ClipData clip = in.getClipData();
        if (clip != null) {
            for (int i = 0; i < clip.getItemCount(); i++) {
                if (clip.getItemAt(i).getUri() != null) set.add(clip.getItemAt(i).getUri());
            }
        }
        return new ArrayList<>(set);
    }

    private void buildUi() {
        int pad = dp(20);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad / 2, pad, pad / 2);
        root.setMinimumWidth(dp(300));

        spinner = new ProgressBar(this);
        root.addView(spinner);

        log = new TextView(this);
        log.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        log.setPadding(0, dp(8), 0, dp(8));
        root.addView(log);

        close = new Button(this);
        close.setText("Close");
        close.setEnabled(false);
        close.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.gravity = Gravity.END;
        root.addView(close, lp);

        // Small banner under the result, kept well away from the Close button.
        int width = Math.round(getResources().getDisplayMetrics().widthPixels * 0.9f);
        FrameLayout adSlot = new FrameLayout(this);
        adSlot.setPadding(0, dp(16), 0, 0);
        root.addView(adSlot, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT));
        setContentView(root);
        getWindow().setLayout(width, ViewGroup.LayoutParams.WRAP_CONTENT);
        setFinishOnTouchOutside(false);
        Ads.showIfAllowed(this, adSlot, width - 2 * pad);
    }

    private void append(String line) {
        ui.post(() -> log.append((log.length() == 0 ? "" : "\n") + line));
    }

    private void done(String summary, boolean allGood) {
        spinner.setVisibility(android.view.View.GONE);
        log.append((log.length() == 0 ? "" : "\n\n") + summary);
        close.setEnabled(true);
        setFinishOnTouchOutside(true);
        if (allGood) ui.postDelayed(this::finish, 4000);
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
