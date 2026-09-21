**From GitHub to Odoo**, once a repository is linked and its webhook is
configured:

- Opening an issue on GitHub creates a task in the linked project. The task
  shows the issue number, its URL and the last synchronization time in the
  **GitHub** tab.
- Editing an issue updates the task title and description.
- Closing an issue marks the task as *Done* (or *Cancelled* when it is
  closed as "not planned"); reopening it puts the task back *In progress*.
  Other open states set in Odoo are kept.
- Comments added, edited or deleted on the issue are mirrored in the task
  chatter as internal notes, prefixed with the GitHub author.
- Pull requests are ignored.
- A comment on an issue that Odoo has not seen yet (for instance one opened
  before the repository was linked) imports that issue as a task.

**From Odoo to GitHub**, when the repository has an API token:

- To publish a task that already exists, choose the repository in the
  **GitHub** tab of the task. The issue is created within a minute.
- Once the task has an issue, changing its title, description or state
  updates the issue. Marking the task *Done* or *Cancelled* closes it.
- Send a message from the chatter with **Send message** to post it as a
  comment on the issue. **Log note** stays in Odoo.
- If GitHub cannot be reached the change is retried automatically (after 1,
  5, 15 minutes, 1 and 4 hours). Failed synchronizations are listed in
  **Project → Configuration → GitHub synchronization**, where they can be
  retried, and a note is added to the task chatter.

If someone edits the same issue on both sides at the same time, the most
recent change wins.
