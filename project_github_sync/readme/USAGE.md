Once a repository is linked and its webhook is configured:

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
