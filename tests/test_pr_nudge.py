from __future__ import annotations

import datetime as dt

import responses
import requests

from pr_nudge import fetch_prs, filter_stale, post_to_slack


def make_pr(number: int, updated: dt.datetime) -> dict:
    return {
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://example.com/pr/{number}",
        "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def test_filter_stale():
    now = dt.datetime.utcnow()
    prs = [make_pr(1, now - dt.timedelta(days=5)), make_pr(2, now)]
    stale = filter_stale(prs, 3)
    assert len(stale) == 1
    assert stale[0]["number"] == 1


@responses.activate
def test_post_to_slack():
    responses.add(responses.POST, "https://hook", status=200)
    post_to_slack("hi", "https://hook")
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_prs_repo():
    session = requests.Session()
    session.token = "t"
    responses.add(
        responses.GET,
        "https://api.github.com/repos/org/repo/pulls",
        json=[make_pr(1, dt.datetime.utcnow())],
        status=200,
    )
    prs = fetch_prs(session, repo="org/repo")
    assert prs and prs[0]["number"] == 1
