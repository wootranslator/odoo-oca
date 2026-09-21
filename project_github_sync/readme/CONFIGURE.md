To link a project with GitHub:

1. Open the project and go to the **GitHub** tab.
2. Add one or more repositories using the `owner/repo` format. A secret is
   generated automatically for each repository.
3. In GitHub, open the repository **Settings → Webhooks → Add webhook** and
   set:

   - **Payload URL**: the URL shown next to the repository in Odoo
     (`https://<your-odoo>/project_github_sync/webhook`).
   - **Content type**: `application/json`.
   - **Secret**: the secret shown next to the repository in Odoo.
   - **Events**: *Let me select individual events* → **Issues** and
     **Issue comments**.

   GitHub sends a `ping` event when the webhook is saved; it should be
   delivered with a `200` response.

If Odoo serves several databases, configure `dbfilter` so that the payload
URL host resolves to a single database.

To unlink a project, remove its repositories (or archive them). Existing
tasks remain as regular tasks.
