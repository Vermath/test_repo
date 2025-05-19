import pytest
import responses
import datetime as dt
from app import app as flask_app # Renamed to avoid conflict with pytest 'app' fixture

# Helper function (duplicated from test_pr_nudge.py for simplicity)
def make_pr(number: int, updated: dt.datetime, labels: list = None) -> dict:
    return {
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://example.com/pr/{number}",
        "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": labels or []
    }

# Pytest fixture for Flask test client
@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

# Test for the /stale-prs endpoint
@responses.activate
def test_stale_prs_route(client, monkeypatch):
    # Simulate environment variables for load_config()
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo") # Using REPO directly for simplicity
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url") # Needed by load_config

    # Mocked PR data
    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    stale_pr_data = make_pr(1, now - dt.timedelta(days=5)) # Stale
    recent_pr_data = make_pr(2, now - dt.timedelta(days=1)) # Not stale

    # Mock GitHub API calls
    # fetch_prs will be called with repo="test/repo"
    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[stale_pr_data, recent_pr_data],
        status=200,
    )

    # Call the /stale-prs endpoint
    response = client.get('/stale-prs')

    # Assertions
    assert response.status_code == 200
    
    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 1" in response_text # Stale PR
    assert stale_pr_data["html_url"] in response_text
    assert "PR 2" not in response_text # Recent PR

    # Check that only the repo pulls endpoint was called
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == "https://api.github.com/repos/test/repo/pulls?state=open&per_page=100&page=1"

# Test for the /stale-prs endpoint when no PRs are stale
@responses.activate
def test_stale_prs_route_no_stale_prs(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    recent_pr_data1 = make_pr(1, now - dt.timedelta(days=1))
    recent_pr_data2 = make_pr(2, now - dt.timedelta(days=2))

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[recent_pr_data1, recent_pr_data2],
        status=200,
    )

    response = client.get('/stale-prs')
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "No stale PRs today!"

# Test for the /stale-prs endpoint with excluded labels
@responses.activate
def test_stale_prs_route_with_excluded_labels(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")
    monkeypatch.setenv("STALE_DAYS", "3")
    monkeypatch.setenv("EXCLUDE_LABELS", "WIP,do-not-merge") # Comma-separated
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    stale_pr_with_excluded_label = make_pr(1, now - dt.timedelta(days=5), labels=[{"name": "WIP"}])
    stale_pr_without_excluded_label = make_pr(2, now - dt.timedelta(days=5))

    responses.add(
        responses.GET,
        "https://api.github.com/repos/test/repo/pulls",
        json=[stale_pr_with_excluded_label, stale_pr_without_excluded_label],
        status=200,
    )

    response = client.get('/stale-prs')
    assert response.status_code == 200
    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 2" in response_text # Should be present
    assert stale_pr_without_excluded_label["html_url"] in response_text
    assert "PR 1" not in response_text # Should be excluded due to 'WIP' label

# Test for when GITHUB_REPO is not set (ORG mode)
@responses.activate
def test_stale_prs_route_org_mode(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake_token")
    monkeypatch.setenv("GITHUB_ORG", "test-org") # Using ORG
    monkeypatch.setenv("STALE_DAYS", "3")
    # GITHUB_REPO is not set
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK", "fake_webhook_url")

    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    stale_pr_data = make_pr(1, now - dt.timedelta(days=5))

    # Mock GitHub API calls for org mode
    responses.add(
        responses.GET,
        "https://api.github.com/orgs/test-org/repos",
        json=[{"full_name": "test-org/repo1"}], # Org has one repo
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/test-org/repo1/pulls",
        json=[stale_pr_data], # That repo has one stale PR
        status=200,
    )

    response = client.get('/stale-prs')
    assert response.status_code == 200
    response_text = response.get_data(as_text=True)
    assert "Stale PRs:" in response_text
    assert "PR 1" in response_text
    assert stale_pr_data["html_url"] in response_text

    assert len(responses.calls) == 2 # Org repos + repo pulls
    assert responses.calls[0].request.url == "https://api.github.com/orgs/test-org/repos?per_page=100&page=1"
    assert responses.calls[1].request.url == "https://api.github.com/repos/test-org/repo1/pulls?state=open&per_page=100&page=1"
