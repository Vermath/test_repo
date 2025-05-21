from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass
class Config:
    github_token: str
    slack_webhook: str
    org: str | None = None
    repo: str | None = None
    stale_days: int = 3
    label_exclude: set[str] = field(default_factory=set)
    not_stale_label: str | None = "not-stale"  # Default label name


def load_config() -> Config:
    token = os.getenv("GITHUB_TOKEN")
    webhook = os.getenv("SLACK_WEBHOOK")
    if not token or not webhook:
        raise RuntimeError("GITHUB_TOKEN and SLACK_WEBHOOK are required")
    org = os.getenv("ORG")
    repo = os.getenv("REPO")
    stale_days = int(os.getenv("STALE_DAYS", "3"))
    if stale_days < 1:
        raise ValueError("STALE_DAYS must be >= 1")
    label_raw = os.getenv("LABEL_EXCLUDE", "")
    label_exclude = {lbl.strip() for lbl in label_raw.split(";") if lbl.strip()}
    if not label_exclude and label_raw:  # Fallback to comma if semicolon yields nothing
        label_exclude = {lbl.strip() for lbl in label_raw.split(",") if lbl.strip()}

    # Load NOT_STALE_LABEL from environment, with a default
    not_stale_label = os.getenv("NOT_STALE_LABEL", "not-stale")
    if not not_stale_label.strip():  # If env var is set to empty string, treat as None
        not_stale_label = None
    else:
        not_stale_label = not_stale_label.strip()

    return Config(token, webhook, org, repo, stale_days, label_exclude, not_stale_label)
