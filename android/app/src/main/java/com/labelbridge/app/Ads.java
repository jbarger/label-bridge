package com.labelbridge.app;

import android.app.Activity;
import android.util.DisplayMetrics;
import android.view.ViewGroup;
import android.widget.FrameLayout;

import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.AdSize;
import com.google.android.gms.ads.AdView;
import com.google.android.gms.ads.MobileAds;
import com.google.android.ump.ConsentInformation;
import com.google.android.ump.ConsentRequestParameters;
import com.google.android.ump.UserMessagingPlatform;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * One small banner ad, never a pop-up. Consent (EEA/UK) goes through Google's
 * User Messaging Platform before any ad is requested.
 */
final class Ads {
    private static final AtomicBoolean started = new AtomicBoolean(false);

    private Ads() { }

    /** Call from the setup screen: asks for consent if the law requires it, then loads the banner. */
    static void gatherConsentThenShow(Activity a, FrameLayout slot, Runnable privacyOptionsChanged) {
        ConsentInformation ci = UserMessagingPlatform.getConsentInformation(a);
        ci.requestConsentInfoUpdate(a, new ConsentRequestParameters.Builder().build(),
                () -> UserMessagingPlatform.loadAndShowConsentFormIfRequired(a, err -> {
                    privacyOptionsChanged.run();
                    if (ci.canRequestAds()) show(a, slot, slot.getWidth());
                }),
                err -> { if (ci.canRequestAds()) show(a, slot, slot.getWidth()); });
        if (ci.canRequestAds()) show(a, slot, slot.getWidth());  // consent from an earlier visit
    }

    /** Banner in a slot; only if consent was already settled (the print popup never asks). */
    static void showIfAllowed(Activity a, FrameLayout slot, int widthPx) {
        if (UserMessagingPlatform.getConsentInformation(a).canRequestAds()) show(a, slot, widthPx);
    }

    static boolean privacyOptionsRequired(Activity a) {
        return UserMessagingPlatform.getConsentInformation(a).getPrivacyOptionsRequirementStatus()
                == ConsentInformation.PrivacyOptionsRequirementStatus.REQUIRED;
    }

    static void showPrivacyOptions(Activity a) {
        UserMessagingPlatform.showPrivacyOptionsForm(a, err -> { });
    }

    private static void show(Activity a, FrameLayout slot, int widthPx) {
        if (a.isFinishing() || slot.getChildCount() > 0) return;
        if (started.compareAndSet(false, true)) {
            new Thread(() -> MobileAds.initialize(a.getApplicationContext(), s -> { }), "ads-init").start();
        }
        DisplayMetrics dm = a.getResources().getDisplayMetrics();
        int w = widthPx > 0 ? widthPx : dm.widthPixels;
        AdView ad = new AdView(a);
        ad.setAdUnitId(BuildConfig.BANNER_ID);
        ad.setAdSize(AdSize.getCurrentOrientationAnchoredAdaptiveBannerAdSize(a, (int) (w / dm.density)));
        slot.addView(ad, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        ad.loadAd(new AdRequest.Builder().build());
    }
}
