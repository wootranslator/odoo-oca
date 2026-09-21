# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError, ValidationError

from .common import ISSUES_URL, FakeResponse, OutboundCase, issue_response


class TestPublishTasks(OutboundCase):
    def test_new_task_is_private_by_default(self):
        task = self.make_task()
        self.assertFalse(task.github_repo_id)
        self.assertFalse(self.jobs(task))

    def test_new_task_published_when_project_opts_in(self):
        self.project.github_push_new_tasks = True
        task = self.make_task(name="Fix the thing", description="<p>Details</p>")
        self.assertEqual(task.github_repo_id, self.repo)
        self.assertEqual(len(self.jobs(task, "task", "pending")), 1)
        mock = self.mock_api(issue_response(7))
        self.run_jobs()
        args, kwargs = mock.call_args
        self.assertEqual(args, ("POST", ISSUES_URL))
        self.assertEqual(kwargs["json"]["title"], "Fix the thing")
        self.assertIn("Details", kwargs["json"]["body"])
        self.assertIn(f"<!-- odoo-sync:task:{task.id} -->", kwargs["json"]["body"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer ghp_secret_token")
        self.assertEqual(task.github_issue_number, 7)
        self.assertEqual(task.github_issue_id, "7007")
        self.assertEqual(task.github_url, "https://github.com/org/repo/issues/7")
        self.assertTrue(task.github_sync_hash)
        self.assertEqual(self.jobs(task).state, "done")
        # storing the answer must not queue another push
        self.assertEqual(len(self.jobs(task)), 1)

    def test_no_token_no_push(self):
        self.repo.api_token = False
        self.project.github_push_new_tasks = True
        task = self.make_task()
        self.assertFalse(self.jobs(task))

    def test_manual_publish(self):
        task = self.make_task()
        mock = self.publish(task)
        self.assertEqual(mock.call_args.args, ("POST", ISSUES_URL))
        self.assertEqual(task.github_issue_number, 7)

    def test_tasks_of_unlinked_projects_are_untouched(self):
        other = self.env["project.project"].create({"name": "Regular"})
        task = self.make_task(project_id=other.id)
        task.name = "Renamed"
        self.assertFalse(self.jobs(task))

    def test_template_tasks_are_not_published(self):
        self.project.github_push_new_tasks = True
        task = self.make_task(is_template=True)
        self.assertFalse(self.jobs(task))

    def test_description_is_sent_as_plain_text(self):
        task = self.make_task(description="<p>Hello <b>world</b></p>")
        mock = self.publish(task)
        body = mock.call_args.kwargs["json"]["body"]
        self.assertIn("Hello", body)
        self.assertNotIn("<p>", body)
        self.assertNotIn("<b>", body)

    def test_publish_closed_task_closes_the_issue(self):
        task = self.make_task(state="1_done")
        mock = self.mock_api(issue_response(7), issue_response(7, status=200))
        task.github_repo_id = self.repo
        self.run_jobs()
        self.assertEqual(
            [call.args[0] for call in mock.call_args_list], ["POST", "PATCH"]
        )
        self.assertEqual(
            mock.call_args_list[1].kwargs["json"],
            {"state": "closed", "state_reason": "completed"},
        )
        self.assertEqual(self.jobs(task).state, "done")

    def test_failure_after_creation_does_not_duplicate_the_issue(self):
        self.mute_sync_errors()
        task = self.make_task(state="1_done")
        self.mock_api(issue_response(7), FakeResponse(500, {"message": "boom"}))
        task.github_repo_id = self.repo
        self.run_jobs()
        job = self.jobs(task)
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempt_count, 1)
        self.assertEqual(task.github_issue_number, 7)
        self.make_due(job)
        mock = self.mock_api(issue_response(7, status=200))
        self.run_jobs()
        self.assertEqual([call.args[0] for call in mock.call_args_list], ["PATCH"])
        self.assertEqual(job.state, "done")


class TestUpdateTasks(OutboundCase):
    def setUp(self):
        super().setUp()
        self.task = self.make_task(name="Original", description="<p>Body</p>")
        self.publish(self.task)

    def test_rename_pushes_a_patch(self):
        self.task.name = "Renamed"
        self.assertEqual(len(self.jobs(self.task, "task", "pending")), 1)
        mock = self.mock_api(issue_response(7, status=200))
        self.run_jobs()
        args, kwargs = mock.call_args
        self.assertEqual(args, ("PATCH", f"{ISSUES_URL}/7"))
        self.assertEqual(kwargs["json"]["title"], "Renamed")
        self.assertEqual(kwargs["json"]["state"], "open")
        self.assertIn("odoo-sync:task", kwargs["json"]["body"])

    def test_unchanged_content_makes_no_request(self):
        self.task.name = "Original"
        mock = self.mock_api()
        self.run_jobs()
        mock.assert_not_called()

    def test_unrelated_changes_are_not_pushed(self):
        pending = len(self.jobs(self.task, state="pending"))
        self.task.priority = "1"
        self.assertEqual(len(self.jobs(self.task, state="pending")), pending)

    def test_changes_are_coalesced(self):
        self.task.name = "One"
        self.task.name = "Two"
        self.assertEqual(len(self.jobs(self.task, "task", "pending")), 1)
        mock = self.mock_api(issue_response(7, status=200))
        self.run_jobs()
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args.kwargs["json"]["title"], "Two")

    def test_state_mapping(self):
        for state, expected in (
            ("1_done", {"state": "closed", "state_reason": "completed"}),
            ("1_canceled", {"state": "closed", "state_reason": "not_planned"}),
            ("01_in_progress", {"state": "open"}),
        ):
            with self.subTest(state=state):
                self.task.state = state
                mock = self.mock_api(issue_response(7, status=200))
                self.run_jobs()
                payload = mock.call_args.kwargs["json"]
                for key, value in expected.items():
                    self.assertEqual(payload[key], value)

    def test_changes_coming_from_github_are_not_pushed(self):
        pending = len(self.jobs(self.task, state="pending"))
        self.task.with_context(github_sync_from_github=True).name = "From GitHub"
        self.assertEqual(len(self.jobs(self.task, state="pending")), pending)

    def test_moving_a_linked_task_to_another_project_is_blocked(self):
        other = self.env["project.project"].create({"name": "Other"})
        with self.assertRaises(ValidationError):
            self.task.project_id = other


class TestEchoAndAdoption(OutboundCase):
    def _issue_payload(
        self, number, body, title="Original", updated="2026-09-21T13:00:00Z"
    ):
        return {
            "action": "edited",
            "issue": {
                "id": 7000 + number,
                "number": number,
                "title": title,
                "body": body,
                "state": "open",
                "html_url": f"https://github.com/org/repo/issues/{number}",
                "updated_at": updated,
            },
        }

    def test_echo_of_our_own_push_does_not_rewrite_the_task(self):
        task = self.make_task(
            name="Original", description="<p>Some <b>rich</b> text</p>"
        )
        mock = self.publish(task)
        description = task.description
        body = mock.call_args.kwargs["json"]["body"].replace("\n", "\r\n")
        self.repo._process_webhook("issues", self._issue_payload(7, body))
        self.assertEqual(task.description, description)
        self.assertEqual(task.github_updated_at.isoformat(), "2026-09-21T13:00:00")
        self.assertFalse(self.jobs(task, state="pending"))

    def test_real_change_on_github_still_wins(self):
        task = self.make_task(name="Original", description="<p>Body</p>")
        self.publish(task)
        self.repo._process_webhook(
            "issues", self._issue_payload(7, "New body", title="Edited on GitHub")
        )
        self.assertEqual(task.name, "Edited on GitHub")
        self.assertIn("New body", task.description)
        self.assertFalse(self.jobs(task, state="pending"))

    def test_issue_created_by_odoo_is_adopted_not_duplicated(self):
        """The webhook can arrive before the API answer is stored."""
        task = self.make_task(name="Original", description="<p>Body</p>")
        task.github_repo_id = self.repo  # queued, not pushed yet
        description = task.description
        body = f"Body\n\n<!-- odoo-sync:task:{task.id} -->"
        self.repo._process_webhook("issues", self._issue_payload(9, body))
        tasks = self.Task.search([("github_repo_id", "=", self.repo.id)])
        self.assertEqual(tasks, task)
        self.assertEqual(task.github_issue_number, 9)
        self.assertEqual(task.description, description)
        # the queued job finds the issue already linked and in sync
        mock = self.mock_api()
        self.run_jobs()
        mock.assert_not_called()
        self.assertEqual(self.jobs(task).state, "done")

    def test_marker_of_a_task_of_another_repo_is_not_adopted(self):
        other_project = self.env["project.project"].create({"name": "Other"})
        other_repo = self.env["project.github.repo"].create(
            {"name": "org/other", "project_id": other_project.id}
        )
        victim = self.make_task(project_id=other_project.id)
        victim.with_context(github_sync_from_github=True).github_repo_id = other_repo
        body = f"x\n\n<!-- odoo-sync:task:{victim.id} -->"
        self.repo._process_webhook("issues", self._issue_payload(11, body))
        self.assertFalse(victim.github_issue_number)
        self.assertEqual(
            len(self.Task.search([("github_repo_id", "=", self.repo.id)])), 1
        )

    def test_webhook_changes_are_not_pushed_back(self):
        self.repo._process_webhook("issues", self._issue_payload(20, "From GitHub"))
        task = self.Task.search([("github_issue_number", "=", 20)])
        self.assertTrue(task)
        self.assertFalse(self.jobs(task))


class TestComments(OutboundCase):
    def setUp(self):
        super().setUp()
        self.task = self.make_task()
        self.publish(self.task)

    def _post(self, subtype="mail.mt_comment", user=None, body="Hello team"):
        task = self.task.with_user(user or self.alice)
        return task.message_post(
            body=body, message_type="comment", subtype_xmlid=subtype
        )

    def test_discussion_message_is_pushed(self):
        message = self._post()
        self.assertEqual(len(self.jobs(self.task, "comment", "pending")), 1)
        mock = self.mock_api(FakeResponse(201, {"id": 555}))
        self.run_jobs()
        args, kwargs = mock.call_args
        self.assertEqual(args, ("POST", f"{ISSUES_URL}/7/comments"))
        self.assertIn("**Alice** (Odoo)", kwargs["json"]["body"])
        self.assertIn("Hello team", kwargs["json"]["body"])
        self.assertIn(f"odoo-sync:message:{message.id}", kwargs["json"]["body"])
        self.assertEqual(message.github_comment_id, "555")

    def test_internal_notes_stay_in_odoo(self):
        self._post(subtype="mail.mt_note")
        self.assertFalse(self.jobs(self.task, "comment"))

    def test_system_and_bot_messages_stay_in_odoo(self):
        self.task._github_note("Something happened")
        self.assertFalse(self.jobs(self.task, "comment"))

    def test_comments_from_github_are_not_pushed_back(self):
        self.repo._process_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": {"id": 7007, "number": 7, "title": "Task from Odoo"},
                "comment": {"id": 99, "body": "hi", "user": {"login": "octocat"}},
            },
        )
        self.assertFalse(self.jobs(self.task, "comment"))

    def test_messages_of_other_models_are_ignored(self):
        self.project.message_post(
            body="x", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        self.assertFalse(self.jobs(kind="comment"))

    def test_published_comment_is_not_mirrored_again(self):
        message = self._post()
        self.mock_api(FakeResponse(201, {"id": 555}))
        self.run_jobs()
        marker = f"<!-- odoo-sync:message:{message.id} -->"
        body = f"**Alice** (Odoo):\n\nHello team\n\n{marker}"
        self.repo._process_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": {"id": 7007, "number": 7, "title": "Task from Odoo"},
                "comment": {"id": 555, "body": body, "user": {"login": "bot"}},
            },
        )
        mirrored = self.env["mail.message"].search([("github_comment_id", "=", "555")])
        self.assertEqual(mirrored, message)

    def test_webhook_arriving_before_the_api_answer(self):
        message = self._post()
        body = f"x\n\n<!-- odoo-sync:message:{message.id} -->"
        self.repo._process_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": {"id": 7007, "number": 7, "title": "Task from Odoo"},
                "comment": {"id": 777, "body": body, "user": {"login": "bot"}},
            },
        )
        self.assertEqual(message.github_comment_id, "777")
        mock = self.mock_api()
        self.run_jobs()
        mock.assert_not_called()
        self.assertEqual(self.jobs(self.task, "comment").state, "done")

    def test_comment_waits_for_the_issue_to_exist(self):
        task = self.make_task(name="Unpublished")
        task.with_context(github_sync_from_github=True).github_repo_id = self.repo
        task.with_user(self.alice).message_post(
            body="Early comment",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        mock = self.mock_api()
        self.run_jobs()
        mock.assert_not_called()
        job = self.jobs(task, "comment")
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempt_count, 1)


class TestFailures(OutboundCase):
    def setUp(self):
        super().setUp()
        self.mute_sync_errors()
        self.task = self.make_task()

    def _publish_with(self, *responses):
        self.mock_api(*responses)
        self.task.github_repo_id = self.repo
        self.run_jobs()
        return self.jobs(self.task)

    def test_server_error_is_retried_with_backoff(self):
        job = self._publish_with(FakeResponse(500, {"message": "boom"}))
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempt_count, 1)
        self.assertIn("500", job.last_error)
        self.assertGreater(job.next_attempt_at, self.env.cr.now())
        self.assertFalse(self.task.github_issue_number)

    def test_job_is_not_retried_before_its_time(self):
        job = self._publish_with(FakeResponse(500, {"message": "boom"}))
        mock = self.mock_api()
        self.run_jobs()
        mock.assert_not_called()
        self.assertEqual(job.attempt_count, 1)

    def test_gives_up_after_too_many_attempts(self):
        self.mock_api(*[FakeResponse(502, {"message": "bad gateway"})] * 10)
        self.task.github_repo_id = self.repo
        job = self.jobs(self.task)
        for _attempt in range(10):
            self.run_jobs()
            if job.state == "failed":
                break
            self.make_due(job)
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.attempt_count, 6)
        note = self.task.message_ids[0].body
        self.assertIn("synchronization failed", note)

    def test_client_errors_fail_immediately(self):
        for status in (401, 403, 404, 422):
            with self.subTest(status=status):
                task = self.make_task()
                self.mock_api(FakeResponse(status, {"message": "nope"}))
                task.github_repo_id = self.repo
                self.run_jobs()
                job = self.jobs(task)
                self.assertEqual(job.state, "failed")
                self.assertEqual(job.attempt_count, 1)
                self.assertIn(str(status), job.last_error)

    def test_rate_limit_honours_retry_after(self):
        response = FakeResponse(403, {"message": "slow down"}, {"Retry-After": "7200"})
        job = self._publish_with(response)
        self.assertEqual(job.state, "pending")
        delta = job.next_attempt_at - self.env.cr.now()
        self.assertGreater(delta.total_seconds(), 7000)

    def test_network_error_is_retried_and_hides_the_token(self):
        import requests

        job = self._publish_with(
            requests.exceptions.ConnectionError("dns ghp_secret_token")
        )
        self.assertEqual(job.state, "pending")
        self.assertNotIn("ghp_secret_token", job.last_error)

    def test_unexpected_error_does_not_block_the_queue(self):
        second = self.make_task(name="Second")
        self.mock_api(RuntimeError("bug"), issue_response(8))
        self.task.github_repo_id = self.repo
        second.github_repo_id = self.repo
        self.run_jobs()
        self.assertEqual(self.jobs(self.task).state, "failed")
        self.assertEqual(self.jobs(second).state, "done")
        self.assertEqual(second.github_issue_number, 8)

    def test_missing_token_fails_the_job(self):
        self.task.github_repo_id = self.repo
        self.repo.api_token = False
        self.run_jobs()
        job = self.jobs(self.task)
        self.assertEqual(job.state, "failed")
        self.assertIn("token", job.last_error)

    def test_retry_action(self):
        job = self._publish_with(FakeResponse(401, {"message": "Bad credentials"}))
        self.assertEqual(job.state, "failed")
        job.action_retry()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.attempt_count, 0)
        self.mock_api(issue_response(7))
        self.run_jobs()
        self.assertEqual(job.state, "done")

    def test_old_done_jobs_are_purged(self):
        self.mock_api(issue_response(7))
        self.task.github_repo_id = self.repo
        self.run_jobs()
        job = self.jobs(self.task)
        job.done_at = "2020-01-01 00:00:00"
        self.Job._gc_done_jobs()
        self.assertFalse(job.exists())


class TestConfiguration(OutboundCase):
    def test_token_is_only_readable_by_managers(self):
        with self.assertRaises(AccessError):
            self.repo.with_user(self.alice).read(["api_token"])
        self.assertEqual(self.repo.api_token, "ghp_secret_token")

    def test_push_needs_a_repository(self):
        project = self.env["project.project"].create({"name": "No repos"})
        with self.assertRaises(ValidationError):
            project.github_push_new_tasks = True

    def test_default_repository_is_the_first_one(self):
        self.assertEqual(self.project.github_default_repo_id, self.repo)

    def test_default_repository_must_belong_to_the_project(self):
        other = self.env["project.project"].create({"name": "Other"})
        other_repo = self.env["project.github.repo"].create(
            {"name": "org/elsewhere", "project_id": other.id}
        )
        with self.assertRaises(ValidationError):
            self.project.github_default_repo_id = other_repo

    def test_default_repository_falls_back_when_archived(self):
        second = self.env["project.github.repo"].create(
            {"name": "org/second", "project_id": self.project.id}
        )
        self.project.github_default_repo_id = second
        second.active = False
        self.assertEqual(self.project.github_default_repo_id, self.repo)
