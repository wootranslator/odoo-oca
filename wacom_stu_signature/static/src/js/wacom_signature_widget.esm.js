/* Copyright 2026 Javier Sánchez de Pedro <https://www.sanchezdepedro.com>
 * License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

import {Component, onMounted, onWillUnmount, useRef, useState} from "@odoo/owl";
import {WacomSDKMissingError, WacomSigCaptX} from "./wacom_sigcaptx.esm";
import {Dialog} from "@web/core/dialog/dialog";
import {SignatureDialog} from "@web/core/signature/signature_dialog";
import {registry} from "@web/core/registry";
import {standardWidgetProps} from "@web/views/widgets/standard_widget_props";
import {useService} from "@web/core/utils/hooks";

// True while a WacomSignatureDialog is open. Prevents OWL duplicate instances
// (OWL may create two component instances from one dialogService.add() call)
// from both initializing the device. The duplicate closes itself via onMounted.
let _dialogOpen = false;

// Serializes any remaining concurrent _initDevice calls as a safety net.
let _initDeviceLock = null;

// ─────────────────────────────────────────────────────────────────────────────
// Wacom SigCaptX Signature Dialog
// ─────────────────────────────────────────────────────────────────────────────

class WacomSignatureDialog extends Component {
    static template = "wacom_stu_signature.WacomSignatureDialog";
    static components = {Dialog};
    static props = {
        signerName: {type: String, optional: true},
        onSignatureCapture: {type: Function},
        onFallback: {type: Function},
        close: {type: Function},
    };

    setup() {
        // If another instance already claimed the dialog, this is an OWL duplicate.
        // We still call all hooks unconditionally (OWL requirement), but skip init.
        this._isDuplicate = _dialogOpen;
        if (!this._isDuplicate) {
            _dialogOpen = true;
        }

        this.state = useState({
            status: "connecting",
            hasSigned: false,
        });
        this.previewCanvas = useRef("previewCanvas");

        if (!this._isDuplicate) {
            this.stu = new WacomSigCaptX();
            this.penDown = false;
            this._initDevice();
        }

        onMounted(() => {
            if (this._isDuplicate) {
                // Close the duplicate after OWL finishes mounting so the primary
                // dialog (with the real device connection) stays visible.
                Promise.resolve().then(() => this.props.close());
            }
        });

        onWillUnmount(() => this._cleanup());
    }

    async _initDevice() {
        if (_initDeviceLock) {
            await _initDeviceLock;
            if (this.state.status === "connecting") {
                this.state.status = "no_device";
            }
            return;
        }

        let _resolve = null;
        _initDeviceLock = new Promise((r) => (_resolve = r));

        try {
            let serviceReady = false;
            try {
                serviceReady = await this.stu.waitForService(12);
            } catch (err) {
                if (err instanceof WacomSDKMissingError) {
                    this.state.status = "no_sdk";
                    return;
                }
                throw err;
            }
            if (!serviceReady) {
                this.state.status = "no_service";
                return;
            }

            let connected = false;
            try {
                connected = await this.stu.connect();
            } catch (err) {
                console.error("[Wacom] connect() threw:", err);
                connected = false;
            }

            if (!connected) {
                this.state.status = "no_device";
                return;
            }
            await this.stu.clearScreen();
            await this.stu.setInking(true);
            await this.stu.showPrompt(this.props.signerName || "");

            this.state.status = "ready";
            this._initCanvas();
        } catch (err) {
            console.error("[Wacom] _initDevice error:", err);
            this.state.status = "no_device";
        } finally {
            _initDeviceLock = null;
            _resolve();
        }
    }

    _initCanvas() {
        setTimeout(() => {
            const canvas = this.previewCanvas.el;
            if (!canvas) return;

            const ctx = canvas.getContext("2d");
            ctx.strokeStyle = "#000000";
            ctx.lineWidth = 2;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";

            const caps = this.stu.caps;
            const scaleX = canvas.width / (caps.tabletMaxX || caps.screenWidth);
            const scaleY = canvas.height / (caps.tabletMaxY || caps.screenHeight);

            this.stu.startPenData((msg) => {
                const px = Math.round(msg.x * scaleX);
                const py = Math.round(msg.y * scaleY);

                if (msg.sw) {
                    if (this.penDown) {
                        ctx.lineTo(px, py);
                        ctx.stroke();
                    } else {
                        ctx.beginPath();
                        ctx.moveTo(px, py);
                        this.penDown = true;
                    }
                    if (!this.state.hasSigned) this.state.hasSigned = true;
                } else if (this.penDown) {
                    ctx.beginPath();
                    this.penDown = false;
                }
            });
        }, 80);
    }

    async _cleanup() {
        if (this._isDuplicate) return;
        _dialogOpen = false;
        if (this.stu) await this.stu.disconnect();
    }

    async onClear() {
        this.state.hasSigned = false;
        this.penDown = false;
        const canvas = this.previewCanvas.el;
        if (canvas) {
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
        await this.stu.clearScreen();
        await this.stu.showPrompt(this.props.signerName || "");
    }

    onCancel() {
        this.props.close();
    }

    async onAccept() {
        if (!this.state.hasSigned) return;
        const dataUrl = this.previewCanvas.el.toDataURL("image/png");
        await this.props.onSignatureCapture(dataUrl);
        this.props.close();
    }

    async onRetry() {
        _initDeviceLock = null;
        this.state.status = "connecting";
        this.state.hasSigned = false;
        this.penDown = false;
        this.stu = new WacomSigCaptX();
        await this._initDevice();
    }

    onFallback() {
        this.props.close();
        this.props.onFallback();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Overridden Signature Widget
// ─────────────────────────────────────────────────────────────────────────────

class WacomSignatureWidget extends Component {
    static template = "web.SignatureWidget";
    static props = {
        ...standardWidgetProps,
        fullName: {type: String, optional: true},
        highlight: {type: Boolean, optional: true},
        string: {type: String},
        signatureField: {type: String, optional: true},
    };

    setup() {
        this.dialogService = useService("dialog");
        this.orm = useService("orm");
    }

    _getSignerName() {
        const {fullName, record} = this.props;
        if (!fullName) return undefined;
        const data = record.data[fullName];
        const field = record.fields[fullName];
        if (field?.type === "many2one") return data?.[1] || undefined;
        return data || undefined;
    }

    async onClickSignature() {
        await this.props.record.save();
        const signerName = this._getSignerName();

        const openFallback = () => {
            this.dialogService.add(SignatureDialog, {
                defaultName: signerName,
                nameAndSignatureProps: {
                    mode: "draw",
                    displaySignatureRatio: 3,
                    signatureType: "signature",
                    noInputName: true,
                    defaultFont: this.props.defaultFont,
                },
                uploadSignature: ({signatureImage}) => this._upload(signatureImage),
            });
        };

        this.dialogService.add(WacomSignatureDialog, {
            signerName,
            onSignatureCapture: (dataUrl) => this._upload(dataUrl),
            onFallback: openFallback,
        });
    }

    async _upload(dataUrl) {
        const base64 = dataUrl.split(",")[1];
        const {model, resModel, resId} = this.props.record;
        await this.orm.write(resModel, [resId], {
            [this.props.signatureField]: base64,
        });
        await this.props.record.load();
        model.notify();
    }
}

registry.category("view_widgets").add(
    "signature",
    {
        component: WacomSignatureWidget,
        extractProps: ({attrs}) => ({
            fullName: attrs.full_name,
            highlight: Boolean(attrs.highlight),
            string: attrs.string,
            signatureField: attrs.signature_field || "signature",
        }),
    },
    {force: true}
);
