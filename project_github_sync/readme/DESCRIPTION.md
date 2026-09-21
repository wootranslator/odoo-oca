This module lets you link Odoo projects with GitHub repositories so that
each team can work in its preferred tool.

The link is **optional and per project**. A project without any linked
repository is a regular Odoo project and is never touched by this module.

For linked projects, GitHub issues are mirrored as Odoo tasks through a
signed webhook (GitHub → Odoo):

- opening, editing, closing and reopening an issue creates or updates the
  task (title, description, link to the issue and done / cancelled state);
- comments on the issue are mirrored in the task chatter;
- deliveries are idempotent, tolerate out-of-order events and are rejected
  unless they carry a valid HMAC signature.

The other direction (Odoo → GitHub) is planned, see the roadmap.
