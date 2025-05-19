# AGENTS.md

## Project: **PR Nudge** – Daily Slack digest of stale pull‑requests
A lightweight Python service that fetches open pull‑requests from GitHub (or GitLab), filters ones with **no commits or comments in the last _N_ days** (default = 3), formats an **interactive Markdown digest with action buttons**, and posts it to a Slack channel via an **Incoming Webhook**.

---

### 1. Suggested Repository Layout

| Path | Purpose |
|------|---------|
| `pr_nudge.py` | Main entry‑point. Contains: `fetch_prs()`, `filter_stale()`, `build_message()`, `post_to_slack()`, and a thin `main()` wrapper. |
| `config.py` | Reads env‑vars, provides defaults, and validates required settings. |
| `tests/` | All unit tests (pytest). |
| `tests/test_pr_nudge.py` | Mocks GitHub & Slack HTTP calls; asserts core behaviours. |
| `requirements.txt` | Runtime deps (`requests`, `python‑dotenv`, `pytest`, `responses`, `ruff`, `black`). |
| `Dockerfile` *(optional)* | Containerised run‐time (python:slim). |

---

### 2. Quick‑start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXX
export SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
export ORG=my‑org           # or set REPO=my‑org/my‑repo
export STALE_DAYS=3         # optional; default = 3
python pr_nudge.py
```

**Tip:** Only *one* of `ORG` or `REPO` is required.  
If `ORG` is provided, the script targets **all** repositories underneath that organisation.

---

### 3. Environment Variables

| Name | Required | Example | Notes |
|------|----------|---------|-------|
| `GITHUB_TOKEN` | ✅ | `ghp_abcd…` | Needs `repo:read` and `public_repo` (or `repo` for private) scopes if using "Mark Not Stale". |
| `SLACK_WEBHOOK` | ✅ | `https://hooks.slack.com/services/T/B/KEY` | Channel is configured on Slack side. |
| `ORG` | ⬜ | `openai` | Query every repo in an org. |
| `REPO` | ⬜ | `openai/gym` | Target a single repo. |
| `STALE_DAYS` | ⬜ | `5` | Integer ≥ 1. Default = 3. |
| `NOT_STALE_LABEL` | ⬜ | `not-stale` | Label to apply when "Mark Not Stale" is clicked. PRs with this label are also automatically excluded from nudges. If set to an empty string, the "Mark Not Stale" button will not apply any label. Default: "not-stale". |

---

### 4. Testing & Quality Gates

* **Run all tests**

  ```bash
  pytest -q
  ```

* **Static analysis / formatting**

  ```bash
  ruff .        # lints
  black --check .  # formatting
  ```

CI (GitHub Actions) **fails** if either command returns a non‑zero exit code.

---

### 5. How to Extend

1. **Label filtering** – Add `LABEL_EXCLUDE="WIP,experimental"` to skip PRs with these labels. PRs with the `NOT_STALE_LABEL` (see Environment Variables) are also automatically excluded.
2. **Cron / Scheduler** – Deploy via GitHub Actions (`workflow_dispatch` + `schedule`) or a platform‑cron.  
3. **Interactive Web UI & Slack Buttons** – The project includes a basic Flask application (`app.py`) that not only exposes stale PRs via a web endpoint but also enables interactive Slack messages.

    *   **Interactive Buttons**: When stale PRs are posted to Slack, each PR will have action buttons:
        *   **Snooze 1d**: Temporarily hides the PR from nudges for 1 day.
        *   **Snooze 7d**: Temporarily hides the PR from nudges for 7 days.
        *   **Mark Not Stale**: Applies the `NOT_STALE_LABEL` (e.g., "not-stale") to the PR on GitHub. PRs with this label will be excluded from future nudges. Requires the `GITHUB_TOKEN` to have appropriate write permissions for labels (e.g., `public_repo` or `repo` scope).
    *   **Snooze Behavior**: The snooze functionality currently uses an in-memory store. This means snoozed PRs will be reset if the Flask application restarts. For persistent snoozing, a database or external store would be required.
    *   **Environment Variables**: The Flask app uses the same environment variables as the `pr_nudge.py` script (see section 3). Ensure these are set in your environment before running the app.
    *   **Running the app**:
        ```bash
        python app.py
        ```
    *   This will start a Flask development server (usually on port 5000 by default). The `/stale-prs` endpoint provides the raw data, while `/slack/interactive` handles button clicks.
    *   **Enabling Slack Interactivity**: To use the interactive buttons, you need to configure your Slack App:
        1.  Go to your Slack App's settings page (usually at `api.slack.com/apps`).
        2.  Navigate to the "Interactivity & Shortcuts" section in the sidebar.
        3.  Toggle "Interactivity" to **On**.
        4.  In the "Request URL" field, enter the publicly accessible URL for the `/slack/interactive` endpoint of your running Flask application. For example, if your app is hosted at `https://my-pr-nudge.example.com`, this URL would be `https://my-pr-nudge.example.com/slack/interactive`.
        5.  Save the changes.
            *Note: For local development, you might need to use a tunneling service like `ngrok` to expose your local Flask app to Slack.*

---

### 6. Internals Cheat‑Sheet

| Function | I/O | Notes |
|----------|-----|-------|
| `fetch_prs(session, *, org=None, repo=None)` | → `list[dict]` | Calls GitHub REST, paginated, returns raw PR JSON. |
| `filter_stale(prs, stale_days, *, exclude_labels=None, snooze_data=None)` | → `list[dict]` | Uses `updated_at`. Filters by labels and active snoozes. Cleans expired snoozes from `snooze_data`. |
| `build_message(stale_prs)` | → `dict` | Returns Slack Block Kit JSON (as a Python dict) for an interactive message. |
| `post_to_slack(message, webhook_url)` | → `None` | HTTP POSTs the Block Kit message; raises on non‑2xx. |

Each helper is **pure / deterministic** except for I/O; this enables fast unit testing.

---

### 7. Conventions & Style Guide

* **Python ≥ 3.12**
* Use **type hints** everywhere (`mypy` friendly).
* External HTTP interactions go through a **single `requests.Session`** instance to ease mocking.
* Avoid global state; config is passed explicitly or read once in `main()`.
* Keep the script under **150 LOC** (excluding tests).

---

### 8. How Codex Agents Should Work Here

1. **Install deps & run tests** (`pytest`, `ruff`, `black --check`).
2. Make edits on a new branch; run tests + lint locally.
3. Commit, push, open a PR. Use the PR template auto‑generated by GitHub (`.github/PULL_REQUEST_TEMPLATE.md`).
4. Ensure all CI checks pass before merging.

---

Happy hacking! 🎉
