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
    if not label_exclude and label_raw:
        label_exclude = {lbl.strip() for lbl in label_raw.split(",") if lbl.strip()}
    return Config(token, webhook, org, repo, stale_days, label_exclude)
