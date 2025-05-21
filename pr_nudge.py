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
    prs: Iterable[dict],
    stale_days: int,
    *,
    exclude_labels: set[str] | None = None,
    snooze_data: dict | None = None,
) -> list[dict]:
    now_utc = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    cutoff = now_utc - dt.timedelta(days=stale_days)
    stale: list[dict] = []
    labels = exclude_labels or set()

    active_snooze_data = snooze_data or {}

    # Clean up expired snoozes from the provided snooze_data dictionary
    # This modifies the dict in-place if it's passed from app.py
    if active_snooze_data:
        for pr_url, expiry_iso_str in list(
            active_snooze_data.items()
        ):  # Iterate over a copy for safe deletion
            try:
                expiry_dt = dt.datetime.fromisoformat(expiry_iso_str)
                if now_utc > expiry_dt:
                    del active_snooze_data[pr_url]
                    print(
                        f"Cleaned up expired snooze for PR (in filter_stale): {pr_url}"
                    )
            except ValueError:
                # Handle cases where the ISO string might be malformed, though unlikely
                print(
                    f"Warning: Malformed snooze expiry string for {pr_url}: {expiry_iso_str}"
                )
                # Optionally, remove the malformed entry
                del active_snooze_data[pr_url]

    for pr in prs:
        pr_url = pr.get("html_url")

        # Check if PR is snoozed
        if pr_url and pr_url in active_snooze_data:
            # Snooze is active, skip this PR
            # No need to check expiry here again as cleanup is done above
            print(f"PR {pr_url} is currently snoozed. Skipping.")
            continue

        if labels and any(label["name"] in labels for label in pr.get("labels", [])):
            continue

        updated = dt.datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        if updated < cutoff:
            stale.append(pr)
    return stale


def build_message(stale_prs: Iterable[dict]) -> dict:
    if not stale_prs:
        return {
            "text": "No stale PRs today!",  # Fallback text
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "🎉 No stale PRs today!"},
                }
            ],
        }

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Stale Pull Requests"},
        },
        {"type": "divider"},
    ]

    fallback_text_lines = ["Stale PRs:"]

    for i, pr in enumerate(stale_prs):
        title = pr["title"]
        url = pr["html_url"]
        updated_at = pr["updated_at"]

        fallback_text_lines.append(f"- {title} ({url}) last updated {updated_at}")

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"- <{url}|{title}> (last updated {updated_at})",
                },
            }
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Snooze 1d",
                            "emoji": True,
                        },
                        "value": url,
                        "action_id": "snooze_1d",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Snooze 7d",
                            "emoji": True,
                        },
                        "value": url,
                        "action_id": "snooze_7d",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Mark Not Stale",
                            "emoji": True,
                        },
                        "value": url,
                        "action_id": "mark_not_stale",
                    },
                ],
            }
        )
        # Add a divider if it's not the last PR
        if i < len(list(stale_prs)) - 1:  # Need to convert iterable to list to get len
            blocks.append({"type": "divider"})

    return {"text": "\n".join(fallback_text_lines), "blocks": blocks}  # Fallback text


def post_to_slack(message: dict, webhook_url: str) -> None:  # Changed message type hint
    r = requests.post(webhook_url, json=message)  # Send the dict as JSON
    r.raise_for_status()


def main() -> None:
    cfg = load_config()
    session = requests.Session()
    session.headers["Authorization"] = f"token {cfg.github_token}"

    # Prepare exclude_labels set
    current_exclude_labels = set(
        cfg.label_exclude
    )  # Start with user-defined exclude_labels
    if cfg.not_stale_label:
        current_exclude_labels.add(cfg.not_stale_label)
        print(
            f"Automatically excluding PRs with label (in pr_nudge.py): {cfg.not_stale_label}"
        )

    prs = fetch_prs(session, org=cfg.org, repo=cfg.repo)
    # Pass None for snooze_data as the script doesn't manage an interactive snooze store
    stale = filter_stale(
        prs, cfg.stale_days, exclude_labels=current_exclude_labels, snooze_data=None
    )
    msg = build_message(stale)
    post_to_slack(msg, cfg.slack_webhook)


if __name__ == "__main__":
    main()
