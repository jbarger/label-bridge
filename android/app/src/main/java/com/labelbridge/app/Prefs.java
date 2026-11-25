package com.labelbridge.app;

import android.content.Context;
import android.content.SharedPreferences;

/** Saved pairing: the PC's address and the pairing code from config.json. */
final class Prefs {
    static final int DEFAULT_PORT = 8765;

    private final SharedPreferences sp;

    Prefs(Context c) {
        sp = c.getSharedPreferences("pairing", Context.MODE_PRIVATE);
    }

    String host() { return sp.getString("host", ""); }
    int port() { return sp.getInt("port", DEFAULT_PORT); }
    String code() { return sp.getString("code", ""); }

    void setHost(String host, int port) {
        sp.edit().putString("host", host.trim()).putInt("port", port).apply();
    }

    void setCode(String code) {
        sp.edit().putString("code", code.trim().toUpperCase()).apply();
    }

    /** Name of the PC's label printer, from the last successful connection test. */
    String printerName() { return sp.getString("printer", ""); }

    void setPrinterName(String name) {
        sp.edit().putString("printer", name == null ? "" : name).apply();
    }

    boolean isPaired() { return !code().isEmpty(); }
}
