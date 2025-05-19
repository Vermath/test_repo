from __future__ import annotations

import datetime as dt
from typing import Iterable
import requests
from config import load_config


GITHUB_API = "https://api.github.com"


def fetch_prs(
    session: requests.Session, *, org: str | None = None, repo: str | None = None
) -> list[dict]:
    if not org and not repo:
        raise ValueError("One of org or repo must be provided")

    headers = {
        "Authorization": f"token {session.token}",
        "Accept": "application/vnd.github+json",
    }
    session.headers.update(headers)
    repos: list[str] = []
    if repo:
        repos.append(repo)
    else:
        page = 1
        while True:
            r = session.get(
                f"{GITHUB_API}/orgs/{org}/repos", params={"per_page": 100, "page": page}
            )
            r.raise_for_status()
            data = r.json()
            repos.extend(item["full_name"] for item in data)
            if len(data) < 100:
                break
            page += 1

    prs: list[dict] = []
    for full_name in repos:
        page = 1
        while True:
            r = session.get(
                f"{GITHUB_API}/repos/{full_name}/pulls",
                params={"state": "open", "per_page": 100, "page": page},
            )
            r.raise_for_status()
            data = r.json()
            prs.extend(data)
            if len(data) < 100:
                break
            page += 1
    return prs


def filter_stale(
    prs: Iterable[dict], stale_days: int, *, exclude_labels: set[str] | None = None
) -> list[dict]:
    cutoff = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) - dt.timedelta(
        days=stale_days
    )
    stale: list[dict] = []
    labels = exclude_labels or set()
    for pr in prs:
        if labels and any(label["name"] in labels for label in pr.get("labels", [])):
            continue
        updated = dt.datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        if updated < cutoff:
            stale.append(pr)
    return stale


def build_message(stale_prs: Iterable[dict]) -> str:
    if not stale_prs:
        return "No stale PRs today!"
    lines = ["Stale PRs:\n"]
    for pr in stale_prs:
        title = pr["title"]
        url = pr["html_url"]
        lines.append(f"- <{url}|{title}> (last updated {pr['updated_at']})")
    return "\n".join(lines)


def post_to_slack(message: str, webhook_url: str) -> None:
    r = requests.post(webhook_url, json={"text": message})
    r.raise_for_status()


def main() -> None:
    cfg = load_config()
    session = requests.Session()
    session.headers['Authorization'] = f"token {cfg.github_token}"
    prs = fetch_prs(session, org=cfg.org, repo=cfg.repo)
    stale = filter_stale(prs, cfg.stale_days, exclude_labels=cfg.label_exclude)
    msg = build_message(stale)
    post_to_slack(msg, cfg.slack_webhook)


if __name__ == "__main__":
    main()
