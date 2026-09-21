- Odoo → GitHub: queued API calls with retries and a synchronization log,
  reusing the `github_sync_from_github` context flag already set by the
  webhook to avoid echoing changes back.
- Comment synchronization from Odoo to GitHub.
- Mapping of Odoo stages to GitHub Projects v2 Status columns.
- Mapping of Odoo users to GitHub logins (assignees) and of GitHub labels to
  task tags.
- Render the GitHub Markdown of issue bodies and comments instead of
  showing it as plain text.
