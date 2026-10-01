This module talks to the pad through Wacom's **SigCaptX** service and Wacom's
**STU SDK** JavaScript library. Neither is distributed with this module.

**On each Windows PC with a pad connected**

1. Download the *STU SDK for Windows Desktop* from
   [developer.wacom.com](https://developer.wacom.com) and install SigCaptX
   (MSI installer). It runs a local service on `wss://localhost:9000`.
2. Connect the pad via USB.

**On the Odoo server (once)**

`wgssStuSdk.js` is proprietary to Wacom and is not included in this repository.
Take it from the JavaScript samples of the Wacom STU SDK and copy it to:

    wacom_stu_signature/static/lib/wacom/wgssStuSdk.js

Until the file is in place, the signature dialog shows a warning and falls
back to signing with the mouse. No restart is needed after copying it: the
file is loaded on demand when the dialog opens.
