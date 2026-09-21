This module lets you link Odoo projects with GitHub repositories so that
each team can work in its preferred tool.

The link is **optional and per project**. A project without any linked
repository is a regular Odoo project and is never touched by this module.

**GitHub → Odoo** (signed webhook):

- opening, editing, closing and reopening an issue creates or updates the
  task (title, description, link to the issue and done / cancelled state);
- comments on the issue are mirrored in the task chatter;
- deliveries are idempotent, tolerate out-of-order events and are rejected
  unless they carry a valid HMAC signature.

**Odoo → GitHub** (needs an API token on the repository):

- tasks are published as issues, either one by one or automatically for
  every new task of a project;
- changes of title, description and state are pushed to the issue;
- messages sent from the task chatter ("Send message") are posted as
  comments; internal notes never leave Odoo;
- pushes go through a queue processed by a cron job, with retries and a
  synchronization log, so an unavailable GitHub never blocks users.

Both directions recognize their own echoes, so nothing loops.
