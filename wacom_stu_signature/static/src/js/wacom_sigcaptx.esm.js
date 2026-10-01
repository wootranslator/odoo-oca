/* Copyright 2026 Javier Sánchez de Pedro <https://www.sanchezdepedro.com>
 * License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

/**
 * Wacom SigCaptX wrapper for the STU series.
 *
 * q.js and wgssStuSdk.js are loaded dynamically as classic <script> tags
 * to avoid AMD/rollup conflicts in Odoo's ES module bundle.
 * SigCaptX must be installed on the Windows PC: it runs a local service on
 * wss://localhost:9000. wgssStuSdk.js is proprietary to Wacom and is not
 * shipped with this module: see readme/INSTALL.md.
 */
import {_t} from "@web/core/l10n/translation";

export class WacomSDKMissingError extends Error {}

// Cache promises per src so concurrent callers share the same load
const _scriptPromises = {};

function _loadScript(src) {
    if (_scriptPromises[src]) return _scriptPromises[src];
    _scriptPromises[src] = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(s);
    });
    return _scriptPromises[src];
}

// Singleton promise — all concurrent callers share the same load sequence
let _sdkPromise = null;

function _ensureSDK() {
    if (_sdkPromise) return _sdkPromise;
    _sdkPromise = (async () => {
        if (window.WacomGSS) return;
        const base = "/wacom_stu_signature/static/lib";
        await _loadScript(`${base}/q/q.js`);
        try {
            await _loadScript(`${base}/wacom/wgssStuSdk.js`);
        } catch {
            throw new WacomSDKMissingError("wgssStuSdk.js not found");
        }
    })().catch((err) => {
        // Allow a retry once the file has been copied into place
        _sdkPromise = null;
        delete _scriptPromises["/wacom_stu_signature/static/lib/wacom/wgssStuSdk.js"];
        throw err;
    });
    return _sdkPromise;
}

export class WacomSigCaptX {
    constructor() {
        this.tablet = null;
        this.intf = null;
        this.caps = null;
        this.encodingMode = null;
        this.reportHandler = null;
    }

    static isAvailable() {
        return typeof window.WacomGSS !== "undefined";
    }

    static isServiceReady() {
        return WacomSigCaptX.isAvailable() && window.WacomGSS.STU.isServiceReady();
    }

    /** Load SDK scripts then wait up to maxRetries seconds for SigCaptX service */
    async waitForService(maxRetries = 12) {
        await _ensureSDK();
        for (let i = 0; i < maxRetries; i++) {
            const ready = WacomSigCaptX.isServiceReady();
            if (ready) return true;
            await new Promise((r) => setTimeout(r, 1000));
        }
        return false;
    }

    /** Connect to the first available STU device */
    async connect() {
        const devices = await window.WacomGSS.STU.getUsbDevices();
        if (!devices || devices.length === 0) return false;

        this.intf = new window.WacomGSS.STU.UsbInterface();
        await this.intf.Constructor();

        const result = await this.intf.connect(devices[0], false);
        if (result.value !== 0) {
            return false;
        }

        this.tablet = new window.WacomGSS.STU.Tablet();
        await this.tablet.Constructor(this.intf);

        this.caps = await this.tablet.getCapability();

        // Use encodingFlag directly from getCapability — simulateEncodingFlag destroys
        // the UsbInterface session on STU-500 as a side effect, so we skip it.
        // STU-500 reports encodingFlag=0 (1-bit monochrome only).
        const p = new window.WacomGSS.STU.Protocol();
        const enc = this.caps.encodingFlag;
        if (enc & p.EncodingFlag.EncodingFlag_24bit) {
            this.encodingMode = p.EncodingMode.EncodingMode_24bit;
        } else if (enc & p.EncodingFlag.EncodingFlag_16bit) {
            this.encodingMode = p.EncodingMode.EncodingMode_16bit;
        } else {
            this.encodingMode = p.EncodingMode.EncodingMode_1bit;
        }

        return true;
    }

    /** Render a signing prompt on the STU screen */
    async showPrompt(signerName) {
        const w = this.caps.screenWidth;
        const h = this.caps.screenHeight;

        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");

        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, w, h);

        ctx.fillStyle = "#222222";
        ctx.font = `bold ${Math.round(h * 0.055)}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(_t("Sign here"), w / 2, Math.round(h * 0.12));

        if (signerName) {
            ctx.font = `${Math.round(h * 0.04)}px sans-serif`;
            ctx.fillStyle = "#555555";
            ctx.fillText(signerName, w / 2, Math.round(h * 0.2));
        }

        // Signature line
        const lineY = Math.round(h * 0.78);
        ctx.strokeStyle = "#aaaaaa";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(Math.round(w * 0.06), lineY);
        ctx.lineTo(Math.round(w * 0.94), lineY);
        ctx.stroke();

        ctx.fillStyle = "#999999";
        ctx.font = `${Math.round(h * 0.04)}px sans-serif`;
        ctx.textAlign = "left";
        ctx.fillText("X", Math.round(w * 0.07), lineY + Math.round(h * 0.07));

        const imgDataUrl = canvas.toDataURL("image/jpeg", 0.9);
        const flatData = await window.WacomGSS.STU.ProtocolHelper.resizeAndFlatten(
            imgDataUrl,
            0,
            0,
            0,
            0,
            w,
            h,
            this.encodingMode,
            1,
            false,
            0,
            true
        );
        await this.tablet.writeImage(this.encodingMode, flatData);
    }

    async clearScreen() {
        if (this.tablet) await this.tablet.setClearScreen();
    }

    async setInking(enabled) {
        if (this.tablet) await this.tablet.setInkingMode(enabled ? 1 : 0);
    }

    /**
     * Start receiving pen data.
     * onPenData(msg) is called with { sw, rdy, x, y } - x/y in tablet units.
     * Use caps.tabletMaxX / tabletMaxY to scale to pixels.
     */
    async startPenData(onPenData) {
        this.reportHandler = new window.WacomGSS.STU.ProtocolHelper.ReportHandler();
        this.reportHandler.onReportPenData = onPenData;
        await this.reportHandler.startReporting(this.tablet, false);
    }

    async stopPenData() {
        if (this.reportHandler) {
            try {
                await this.reportHandler.stopReporting();
            } catch {
                // Best effort: the pad may already be gone
            }
            this.reportHandler = null;
        }
    }

    async disconnect() {
        try {
            await this.stopPenData();
            await this.setInking(false);
            await this.clearScreen();
            if (this.tablet) {
                await this.tablet.disconnect();
                this.tablet = null;
                this.intf = null;
            }
        } catch {
            // Best effort: the pad may already be unplugged
        }
    }
}
