- Make the cron interval and send time configurable instead of the fixed
  daily run at 20:00.
- Add a "no changes today" digest option per pricelist (currently
  pricelists with no changes are simply skipped).
- Send the digest body in each recipient's own language. Right now
  `_build_digest_rows` is rendered once in the language of the user
  running the cron, so all recipients on a pricelist get the same
  language regardless of their own preference.
- Port to Odoo 20.0.
