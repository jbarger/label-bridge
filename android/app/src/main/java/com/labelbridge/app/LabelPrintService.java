package com.labelbridge.app;

import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.print.PrintAttributes;
import android.print.PrinterCapabilitiesInfo;
import android.print.PrinterId;
import android.print.PrinterInfo;
import android.printservice.PrintJob;
import android.printservice.PrintService;
import android.printservice.PrinterDiscoverySession;

import java.io.FileInputStream;
import java.util.Collections;
import java.util.List;

/**
 * Makes the PC's label printer appear in Android's ⋮ → Print menu.
 * Android renders whatever is being printed to a PDF; we send that PDF to the PC,
 * which crops it to the label and prints it, exactly like the Share route.
 */
public class LabelPrintService extends PrintService {
    private static final String LOCAL_ID = "pc-label-printer";
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    protected PrinterDiscoverySession onCreatePrinterDiscoverySession() {
        return new Session();
    }

    @Override
    protected void onRequestCancelPrintJob(PrintJob job) {
        job.cancel();
    }

    @Override
    protected void onPrintJobQueued(final PrintJob job) {
        if (!new Prefs(this).isPaired()) {
            job.fail("Open the Label Bridge app and enter the pairing code first.");
            return;
        }
        job.start();
        final String name = job.getDocument().getInfo().getName();
        final ParcelFileDescriptor pfd = job.getDocument().getData();
        new Thread(() -> {
            PrintClient.Result r;
            try (ParcelFileDescriptor fd = pfd;
                 FileInputStream in = new FileInputStream(fd.getFileDescriptor())) {
                byte[] pdf = PrintClient.readFully(in);
                r = new PrintClient(getApplicationContext()).print(pdf, name.toLowerCase().endsWith(".pdf") ? name : name + ".pdf");
            } catch (Exception e) {
                r = new PrintClient.Result(false, "error", "couldn't read the print job: " + e.getMessage());
            }
            final PrintClient.Result res = r;
            main.post(() -> {
                if (job.isCancelled() || job.isCompleted() || job.isFailed()) return;
                if (res.ok) job.complete();
                else job.fail(res.detail);
            });
        }, "print-job").start();
    }

    private final class Session extends PrinterDiscoverySession {
        private PrinterInfo build(int status, String description) {
            PrinterId id = generatePrinterId(LOCAL_ID);
            PrinterCapabilitiesInfo caps = new PrinterCapabilitiesInfo.Builder(id)
                    // Letter first: apps pass full pages through untouched and the PC finds the label.
                    .addMediaSize(PrintAttributes.MediaSize.NA_LETTER, true)
                    .addMediaSize(new PrintAttributes.MediaSize("LABEL_4X6", "4 x 6 in label", 4000, 6000), false)
                    .addResolution(new PrintAttributes.Resolution("r203", "203 dpi", 203, 203), true)
                    .setColorModes(PrintAttributes.COLOR_MODE_MONOCHROME | PrintAttributes.COLOR_MODE_COLOR,
                            PrintAttributes.COLOR_MODE_MONOCHROME)
                    .setMinMargins(PrintAttributes.Margins.NO_MARGINS)
                    .build();
            String printer = new Prefs(LabelPrintService.this).printerName();
            String label = printer.isEmpty() || printer.startsWith("none") || printer.startsWith("PREVIEW")
                    ? "Label printer (Label Bridge)" : printer + " (Label Bridge)";
            PrinterInfo.Builder b = new PrinterInfo.Builder(id, label, status)
                    .setCapabilities(caps);
            if (description != null) b.setDescription(description);
            return b.build();
        }

        @Override
        public void onStartPrinterDiscovery(List<PrinterId> priorityList) {
            addPrinters(Collections.singletonList(build(PrinterInfo.STATUS_IDLE, "via the home PC")));
        }

        /** When the printer is selected, check the PC is reachable so the dialog can say so. */
        @Override
        public void onStartPrinterStateTracking(PrinterId printerId) {
            new Thread(() -> {
                PrintClient.Result r = new PrintClient(getApplicationContext()).ping();
                main.post(() -> {
                    if (isDestroyed()) return;
                    PrinterInfo info;
                    if (!r.ok) info = build(PrinterInfo.STATUS_UNAVAILABLE, "PC not reachable: " + r.detail);
                    else if ("not_ready".equals(r.status)) info = build(PrinterInfo.STATUS_UNAVAILABLE, r.detail);
                    else info = build(PrinterInfo.STATUS_IDLE, "via the home PC");
                    addPrinters(Collections.singletonList(info));
                });
            }, "printer-check").start();
        }

        @Override public void onStopPrinterDiscovery() { }
        @Override public void onValidatePrinters(List<PrinterId> printerIds) { }
        @Override public void onStopPrinterStateTracking(PrinterId printerId) { }
        @Override public void onDestroy() { }
    }
}
