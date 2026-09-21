- Mapping of Odoo stages to GitHub Projects v2 Status columns.
- Mapping of Odoo users to GitHub logins (assignees) and of GitHub labels to
  task tags.
- Render the GitHub Markdown of issue bodies and comments instead of
  showing it as plain text, and send the task description as Markdown.
- Initial import of the existing issues when a repository is linked, and a
  periodic reconciliation to recover deliveries GitHub does not retry.
- Synchronize pull request comments and edited or deleted Odoo comments.
- Authenticate with a GitHub App instead of a personal access token.
