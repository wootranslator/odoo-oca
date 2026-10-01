This module lets users sign documents on a **Wacom STU** signature pad
(STU-430, STU-500, STU-530, STU-540…) directly from the Odoo backend.

It replaces the standard `signature` widget: when a user clicks the signature
field of a delivery order (or of any other form that uses that widget), the
signing prompt is shown on the pad's screen, the signature is mirrored live in
Odoo, and on acceptance it is stored in the record's signature field.

Typical use: a customer collecting goods at the counter signs the delivery
order on the pad, without paper to scan and without a paid e-signature service.

If the pad, the SigCaptX service or the Wacom SDK file is not available, the
dialog says so and offers to sign with the mouse, using Odoo's standard
signature dialog.
