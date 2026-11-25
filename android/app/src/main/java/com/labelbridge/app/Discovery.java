package com.labelbridge.app;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Finds the PC on the Wi-Fi via the _labelprinter._tcp mDNS advertisement. */
final class Discovery {
    private static final String TYPE = "_labelprinter._tcp";

    /** Blocking: returns {host, port} or null. Call off the UI thread. */
    static String[] find(Context ctx, long timeoutMs) {
        final NsdManager nsd = (NsdManager) ctx.getApplicationContext().getSystemService(Context.NSD_SERVICE);
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<String[]> result = new AtomicReference<>();
        final AtomicBoolean resolving = new AtomicBoolean(false);

        NsdManager.DiscoveryListener listener = new NsdManager.DiscoveryListener() {
            @Override public void onStartDiscoveryFailed(String t, int e) { done.countDown(); }
            @Override public void onStopDiscoveryFailed(String t, int e) { }
            @Override public void onDiscoveryStarted(String t) { }
            @Override public void onDiscoveryStopped(String t) { }
            @Override public void onServiceLost(NsdServiceInfo s) { }

            @Override public void onServiceFound(NsdServiceInfo s) {
                if (!resolving.compareAndSet(false, true)) return;
                nsd.resolveService(s, new NsdManager.ResolveListener() {
                    @Override public void onResolveFailed(NsdServiceInfo s2, int e) { resolving.set(false); }

                    @Override public void onServiceResolved(NsdServiceInfo s2) {
                        if (s2.getHost() != null) {
                            result.set(new String[]{s2.getHost().getHostAddress(), String.valueOf(s2.getPort())});
                        }
                        done.countDown();
                    }
                });
            }
        };

        try {
            nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, listener);
            done.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (Exception ignored) {
        } finally {
            try { nsd.stopServiceDiscovery(listener); } catch (Exception ignored) { }
        }
        return result.get();
    }

    private Discovery() { }
}
