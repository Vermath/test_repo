import pytest
import responses
from datetime import (
    datetime,
    timedelta,
    timezone,
)  # Explicit imports for clarity in new tests
import json
from freezegun import freeze_time

from app import (
    app as flask_app,
    snoozed_prs as app_snoozed_prs,
)  # Import global snooze store
from config import Config  # For mocking


# Helper function (duplicated from test_pr_nudge.py for simplicity)
def make_pr(
    number: int, updated: datetime, labels: list = None
) -> dict:  # Use imported datetime
    return {
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://example.com/pr/{number}",
        "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": labels or [],
    }


# Pytest fixture for Flask test client
@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    # Clear the global snooze store before each test that might use it
    app_snoozed_prs.clear()
    with flask_app.test_client() as client:
        yield client
    app_snoozed_prs.clear()  # And after, for good measure


# Test for the /stale-prs endpoint
@responses.activate
def test_stale_prs_route(client, monkeypatch):
    # Simulate environment variables for load_config()
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")  # Using REPO directly for simplicity
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")  # Needed by load_config
    monkeypatch.setenv("NOT_STALE_LABEL", "not-stale-anymore")

    # Mocked PR data
    now = datetime.utcnow().replace(tzinfo=timezone.utc)  # Use imported datetime
    stale_pr_data = make_pr(1, now - timedelta(days=5))  # Stale
    recent_pr_data = make_pr(2, now - timedelta(days=1))  # Not stale
    not_stale_label_pr_data = make_pr(
        3, now - timedelta(days=5), labels=[{"name": "not-stale-anymore"}]
    )

    # Mock GitHub API calls
    # fetch_prs will be called with repo="test/repo"
    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[stale_pr_data, recent_pr_data, not_stale_label_pr_data],
        status=200,
    )

    # Call the /stale-prs endpoint
    response = client.get("/stale-prs")

    # Assertions
    assert response.status_code == 200

    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 1" in response_text  # Stale PR
    assert stale_pr_data["html_url"] in response_text
    assert "PR 2" not in response_text  # Recent PR
    assert "PR 3" not in response_text  # Excluded by NOT_STALE_LABEL

    # Check that only the repo pulls endpoint was called
    assert len(responses.calls) == 1
    assert (
        responses.calls[0].request.url
        == "https://api.github.com/repos/test/repo/pulls?state=open&per_page=100&page=1"
    )


# Test for the /stale-prs endpoint when no PRs are stale
@responses.activate
def test_stale_prs_route_no_stale_prs(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = datetime.utcnow().replace(tzinfo=timezone.utc)  # Use imported datetime
    recent_pr_data1 = make_pr(1, now - timedelta(days=1))
    recent_pr_data2 = make_pr(2, now - timedelta(days=2))

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[recent_pr_data1, recent_pr_data2],
        status=200,
    )

    response = client.get("/stale-prs")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "No stale PRs today!"


# Test for the /stale-prs endpoint with excluded labels
@responses.activate
def test_stale_prs_route_with_excluded_labels(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("EXCLUDE_LABELS", "WIP,do-not-merge")  # Comma-separated
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = datetime.utcnow().replace(tzinfo=timezone.utc)  # Use imported datetime
    stale_pr_with_excluded_label = make_pr(
        1, now - timedelta(days=5), labels=[{"name": "WIP"}]
    )
    stale_pr_without_excluded_label = make_pr(2, now - timedelta(days=5))

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[stale_pr_with_excluded_label, stale_pr_without_excluded_label],
        status=200,
    )

    response = client.get("/stale-prs")
    assert response.status_code == 200
    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 2" in response_text  # Should be present
    assert stale_pr_without_excluded_label["html_url"] in response_text
    assert "PR 1" not in response_text  # Should be excluded due to 'WIP' label


# Test for when GITHUB_REPO is not set (ORG mode)
@responses.activate
def test_stale_prs_route_org_mode(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_ORG", "test-org")  # Using ORG
    monkeypatch.setenv("STALE_DAYS", "3")
    # GITHUB_REPO is not set
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = datetime.utcnow().replace(tzinfo=timezone.utc)  # Use imported datetime
    stale_pr_data = make_pr(1, now - timedelta(days=5))

    # Mock GitHub API calls for org mode
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/test-org/repos",
        json=[{"full_name": "test-org/repo1"}],  # Org has one repo
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/test-org/repo1/pulls",
        json=[stale_pr_data],  # That repo has one stale PR
        status=200,
    )

    response = client.get("/stale-prs")
    assert response.status_code == 200
    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 1" in response_text
    assert stale_pr_data["html_url"] in response_text

    assert len(responses.calls) == 2  # Org repos + repo pulls
    assert (
        responses.calls[0].request.url
        == "https://api.github.com/orgs/test-org/repos?per_page=100&page=1"
    )
    assert (
        responses.calls[1].request.url
        == "https://api.github.com/repos/test-org/repo1/pulls?state=open&per_page=100&page=1"
    )


# Tests for /slack/interactive endpoint


@freeze_time("2023-01-01 12:00:00 UTC")
def test_slack_interactive_snooze_1d(client):
    pr_url_to_snooze = "https://github.com/test/repo/pull/123"
    payload = {
        "actions": [{"action_id": "snooze_1d", "value": pr_url_to_snooze}],
        # Other Slack payload fields can be added if needed by the handler
    }
    response = client.post("/slack/interactive", data={"payload": json.dumps(payload)})
    assert response.status_code == 200
    assert pr_url_to_snooze in app_snoozed_prs

    expected_expiry = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=1)
    assert app_snoozed_prs[pr_url_to_snooze] == expected_expiry.isoformat()


@freeze_time("2023-01-01 12:00:00 UTC")
def test_slack_interactive_snooze_7d(client):
    pr_url_to_snooze = "https://github.com/test/repo/pull/456"
    payload = {"actions": [{"action_id": "snooze_7d", "value": pr_url_to_snooze}]}
    response = client.post("/slack/interactive", data={"payload": json.dumps(payload)})
    assert response.status_code == 200
    assert pr_url_to_snooze in app_snoozed_prs

    expected_expiry = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=7)
    assert app_snoozed_prs[pr_url_to_snooze] == expected_expiry.isoformat()


@responses.activate
@freeze_time("2023-01-01 12:00:00 UTC")
def test_slack_interactive_mark_not_stale(client, monkeypatch):
    pr_url_to_mark = "https://github.com/testowner/testrepo/pull/789"
    not_stale_label = "not-stale-anymore"

    # Mock load_config
    mock_config = Config(
        github_token="fake_gh_token",
        slack_webhook="fake_slack_webhook",
        not_stale_label=not_stale_label,
    )
    monkeypatch.setattr("app.load_config", lambda: mock_config)

    # Mock GitHub API call for adding label
    expected_label_url = (
        "https://api.github.com/repos/testowner/testrepo/issues/789/labels"
    )
    responses.add(
        responses.POST,
        expected_label_url,
        json={"message": "Label added"},  # Mock response from GitHub
        status=200,
    )

    payload = {"actions": [{"action_id": "mark_not_stale", "value": pr_url_to_mark}]}
    response = client.post("/slack/interactive", data={"payload": json.dumps(payload)})

    assert response.status_code == 200
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == expected_label_url
    assert (
        responses.calls[0].request.headers["Authorization"]
        == f"token {mock_config.github_token}"
    )
    assert json.loads(responses.calls[0].request.body) == {"labels": [not_stale_label]}


def test_slack_interactive_missing_payload(client):
    response = client.post("/slack/interactive", data={})  # No 'payload' field
    assert response.status_code == 400
    assert "No payload received" in response.get_data(as_text=True)


def test_slack_interactive_malformed_payload(client):
    response = client.post("/slack/interactive", data={"payload": "this is not json"})
    assert response.status_code == 400
    assert "Invalid JSON payload" in response.get_data(as_text=True)


def test_slack_interactive_missing_action_id(client):
    pr_url = "https://github.com/test/repo/pull/1"
    payload = {"actions": [{"value": pr_url}]}  # Missing action_id
    response = client.post("/slack/interactive", data={"payload": json.dumps(payload)})
    assert response.status_code == 400
    assert "Missing action_id or pr_url" in response.get_data(as_text=True)


def test_slack_interactive_missing_pr_url(client):
    payload = {"actions": [{"action_id": "snooze_1d"}]}  # Missing value (pr_url)
    response = client.post("/slack/interactive", data={"payload": json.dumps(payload)})
    assert response.status_code == 400
    assert "Missing action_id or pr_url" in response.get_data(as_text=True)


@responses.activate
def test_stale_prs_route_with_snoozed_pr(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    stale_pr1 = make_pr(1, now - timedelta(days=5))  # Will be snoozed
    stale_pr2 = make_pr(2, now - timedelta(days=5))  # Will remain stale

    # Snooze PR1
    app_snoozed_prs[stale_pr1["html_url"]] = (now + timedelta(days=1)).isoformat()

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[stale_pr1, stale_pr2],
        status=200,
    )

    response = client.get("/stale-prs")
    assert response.status_code == 200
    response_text = response.get_data(as_text=True)

    assert "PR 2" in response_text  # PR2 should be listed
    assert stale_pr2["html_url"] in response_text
    assert "PR 1" not in response_text  # PR1 should be absent due to snooze
