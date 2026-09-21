To link a project with GitHub:

1. Open the project and go to the **GitHub** tab.
2. Add one or more repositories using the `owner/repo` format. A secret is
   generated automatically for each repository.
3. In GitHub, open the repository **Settings → Webhooks → Add webhook** and
   set:

   - **Payload URL**: the URL shown next to the repository in Odoo
     (`https://<your-odoo>/project_github_sync/webhook`). Check that
     `web.base.url` starts with `https://`: GitHub does not follow
     redirects.
   - **Content type**: `application/json`.
   - **Secret**: the secret shown next to the repository in Odoo.
   - **Events**: *Let me select individual events* → **Issues** and
     **Issue comments**.

   GitHub sends a `ping` event when the webhook is saved; it should be
   delivered with a `200` response.

If Odoo serves several databases, configure `dbfilter` so that the payload
URL host resolves to a single database.

To also send changes from Odoo to GitHub (optional):

1. Create a GitHub *fine-grained personal access token* limited to the
   repository, with read and write access to **Issues**. Prefer a token of a
   dedicated account or bot: GitHub shows it as the author of what Odoo
   writes (Odoo adds the name of the Odoo user in each comment).
2. Paste it in the **API token** column of the repository. Only project
   managers can read it. Without a token, the repository only receives
   changes from GitHub.
3. In the **GitHub** tab of the project, enable **Publish new tasks on
   GitHub** to publish every new task in the *default repository*. Leave it
   off to keep Odoo tasks private and publish them one by one (see Usage).

The queue is processed every minute by the scheduled action *GitHub sync:
push pending changes to GitHub*.

To unlink a project, remove its repositories (or archive them). Existing
tasks remain as regular tasks.
