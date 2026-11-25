package com.labelbridge.app;

import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** Talks to phone_server.py on the PC. All methods block: call off the UI thread. */
final class PrintClient {

    static final class Result {
        final boolean ok;
        final String status;
        final String detail;

        Result(boolean ok, String status, String detail) {
            this.ok = ok; this.status = status; this.detail = detail;
        }
    }

    private final Context ctx;
    private final Prefs prefs;

    PrintClient(Context ctx) {
        this.ctx = ctx;
        this.prefs = new Prefs(ctx);
    }

    Result ping() {
        return withRediscovery(() -> request("/ping", null, null));
    }

    Result print(Uri uri) {
        final byte[] pdf;
        try {
            pdf = readAll(uri);
        } catch (IOException e) {
            return new Result(false, "error", "couldn't read the file: " + e.getMessage());
        }
        return print(pdf, displayName(uri));
    }

    /** Used by the system Print menu (LabelPrintService), which hands over PDF bytes directly. */
    Result print(final byte[] pdf, final String name) {
        return withRediscovery(() -> request("/print", pdf, name));
    }

    static byte[] readFully(InputStream in) throws IOException {
        return readStream(in);
    }

    private interface Call { Result run() throws IOException; }

    /** The PC never answered, so nothing was sent and it's safe to retry elsewhere. */
    private static final class ConnectFailed extends IOException {
        ConnectFailed(IOException cause) { super(cause.getMessage(), cause); }
    }

    /** If the saved address doesn't answer (PC got a new IP), look it up again once and retry. */
    private Result withRediscovery(Call call) {
        if (!prefs.host().isEmpty()) {
            try {
                return call.run();
            } catch (ConnectFailed first) {
                String[] found = Discovery.find(ctx, 4000);
                if (found == null || found[0].equals(prefs.host())) {
                    return new Result(false, "error", "can't reach the PC at " + prefs.host()
                            + ". Is it on, and is this phone on the home Wi-Fi?");
                }
                prefs.setHost(found[0], Integer.parseInt(found[1]));
            } catch (IOException midway) {
                return dropped(midway);
            }
        } else {
            String[] found = Discovery.find(ctx, 6000);
            if (found == null) {
                return new Result(false, "error", "couldn't find the PC on this Wi-Fi. Open Label Bridge and enter its address.");
            }
            prefs.setHost(found[0], Integer.parseInt(found[1]));
        }
        try {
            return call.run();
        } catch (ConnectFailed e) {
            return new Result(false, "error", "can't reach the PC: " + e.getMessage());
        } catch (IOException midway) {
            return dropped(midway);
        }
    }

    /** Never auto-retry once bytes went out: the PC may already have printed it. */
    private static Result dropped(IOException e) {
        return new Result(false, "error", "connection dropped while sending (" + e.getMessage()
                + "). Check the printer before sending this one again.");
    }

    private Result request(String path, byte[] body, String filename) throws IOException {
        URL url = new URL("http://" + prefs.host() + ":" + prefs.port() + path);
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(60000);
        c.setRequestProperty("X-Token", prefs.code());
        if (body != null) {
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setFixedLengthStreamingMode(body.length);
            c.setRequestProperty("Content-Type", "application/pdf");
            c.setRequestProperty("X-Filename", URLEncoder.encode(filename, "UTF-8"));
        }
        try {
            c.connect();
        } catch (IOException e) {
            throw new ConnectFailed(e);
        }
        if (body != null) {
            try (OutputStream out = c.getOutputStream()) {
                out.write(body);
            }
        }
        int code = c.getResponseCode();
        InputStream in = code < 400 ? c.getInputStream() : c.getErrorStream();
        String text = in == null ? "{}" : new String(readStream(in), "UTF-8");
        c.disconnect();
        try {
            JSONObject j = new JSONObject(text);
            if (path.equals("/ping")) {
                boolean ok = j.optBoolean("ok", false);
                if (ok) prefs.setPrinterName(j.optString("printer"));
                if (!ok) return new Result(false, "error", j.optString("detail", "HTTP " + code));
                String host = j.optString("host");
                if (!j.optBoolean("printer_ready", true)) {  // older PCs don't send this
                    return new Result(true, "not_ready", "Connected to " + host
                            + ", but the label printer isn't ready: " + j.optString("printer_problem"));
                }
                return new Result(true, "ok", "Connected to " + host + ", printer: " + j.optString("printer"));
            }
            String status = j.optString("status", "error");
            return new Result("printed".equals(status) || "queued".equals(status), status, j.optString("detail"));
        } catch (Exception e) {
            return new Result(false, "error", "unexpected reply (HTTP " + code + ")");
        }
    }

    private byte[] readAll(Uri uri) throws IOException {
        InputStream in = ctx.getContentResolver().openInputStream(uri);
        if (in == null) throw new IOException("no data");
        return readStream(in);
    }

    private static byte[] readStream(InputStream in) throws IOException {
        try (InputStream is = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = is.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    String displayName(Uri uri) {
        try (Cursor cur = ctx.getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cur != null && cur.moveToFirst() && cur.getString(0) != null) return cur.getString(0);
        } catch (Exception ignored) { }
        String last = uri.getLastPathSegment();
        return last != null ? last : "label.pdf";
    }
}
