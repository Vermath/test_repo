from flask import Flask, request
import json
import re # For parsing PR URL
from datetime import datetime, timedelta, timezone
from pr_nudge import build_message, fetch_prs, filter_stale
from config import load_config, Config # Import Config for type hinting
import requests

app = Flask(__name__)

# GitHub API constants
GITHUB_API_BASE_URL = "https://api.github.com"

# Global store for snoozed PRs: pr_url -> snooze_until_datetime_utc_iso_string
snoozed_prs = {}

@app.route('/stale-prs', methods=['GET'])
def stale_prs_route():
    config: Config = load_config() # Type hint for clarity
    
    session = requests.Session()
    # Use config object attributes directly
    session.headers['Authorization'] = f"token {config.github_token}"
    
    # Clean up expired snoozes (also done in filter_stale, but good for hygiene here too)
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    for pr_url, expiry_iso_str in list(snoozed_prs.items()): # Iterate over a copy
        if now_utc > datetime.fromisoformat(expiry_iso_str):
            del snoozed_prs[pr_url]
            print(f"Cleaned up expired snooze for PR (in /stale-prs): {pr_url}")

    prs = fetch_prs(session, config['github_repo'], config.get('github_user'))
    # Pass the snoozed_prs dictionary to filter_stale
    current_exclude_labels = set(config.label_exclude) # Start with user-defined exclude_labels
    if config.not_stale_label:
        current_exclude_labels.add(config.not_stale_label)
        print(f"Automatically excluding PRs with label: {config.not_stale_label}")

    stale_prs = filter_stale(
        prs, 
        config.stale_days, 
        exclude_labels=current_exclude_labels, # Pass the combined set
        snooze_data=snoozed_prs 
    )
    message = build_message(stale_prs)
    
    return message

@app.route("/slack/interactive", methods=["POST"])
def slack_interactive_endpoint():
    payload_str = request.form.get("payload")
    if not payload_str:
        # Handle error: no payload received
        # Log this occurrence for debugging
        print("Error: No payload received from Slack interactive request.")
        return "Error: No payload received", 400
    
    try:
        payload_dict = json.loads(payload_str)
    except json.JSONDecodeError:
        # Handle error: invalid JSON
        # Log this occurrence for debugging
        print(f"Error: Invalid JSON payload received: {payload_str}")
        return "Error: Invalid JSON payload", 400

    # For now, just print (or log) the payload for inspection
    # In a real application, use proper logging
    print(f"Received Slack interactive payload: {payload_dict}")

    actions = payload_dict.get("actions")
    if not actions or not isinstance(actions, list) or len(actions) == 0:
        print("Error: No actions found in payload")
        return "Error: No actions found in payload", 400

    action = actions[0] # Assuming one action per interaction
    action_id = action.get("action_id")
    pr_url = action.get("value") # PR URL is stored in 'value'

    if not action_id or not pr_url:
        print(f"Error: Missing action_id or pr_url in action: {action}")
        return "Error: Missing action_id or pr_url", 400

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    if action_id == "snooze_1d":
        expiry_time = now_utc + timedelta(days=1)
        snoozed_prs[pr_url] = expiry_time.isoformat()
        print(f"Snoozing PR {pr_url} for 1 day. Expires at: {snoozed_prs[pr_url]}")
    elif action_id == "snooze_7d":
        expiry_time = now_utc + timedelta(days=7)
        snoozed_prs[pr_url] = expiry_time.isoformat()
        print(f"Snoozing PR {pr_url} for 7 days. Expires at: {snoozed_prs[pr_url]}")
    elif action_id == "mark_not_stale":
        print(f"Attempting to mark PR as not stale: {pr_url}")
        # Extract owner, repo, PR number from URL
        match = re.match(r"https:\/\/github\.com\/([^\/]+)\/([^\/]+)\/pull\/(\d+)", pr_url)
        if not match:
            print(f"Error: Could not parse PR URL: {pr_url}")
            return "Error: Invalid PR URL format", 400
        
        owner, repo, pr_number = match.groups()
        cfg: Config = load_config()

        if not cfg.not_stale_label:
            print("Error: NOT_STALE_LABEL is not configured. Cannot apply label.")
            # Optionally inform Slack user via response_url
            return "Error: Not configured to apply 'not stale' label.", 200 # 200 to ack to Slack

        github_session = requests.Session()
        github_session.headers.update({
            "Authorization": f"token {cfg.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28" # Good practice
        })

        labels_url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues/{pr_number}/labels"
        payload = {"labels": [cfg.not_stale_label]}
        
        try:
            response = github_session.post(labels_url, json=payload)
            response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
            print(f"Successfully labeled PR {pr_url} with '{cfg.not_stale_label}'. Status: {response.status_code}")
            # Optionally send ephemeral message to Slack user via payload_dict.get('response_url')
        except requests.exceptions.RequestException as e:
            print(f"Error adding label to PR {pr_url}: {e}")
            # Optionally inform Slack user via response_url
            return f"Error adding label: {e}", 500 # Or 200 to Slack and log error

    # Acknowledge receipt to Slack
    return "", 200

if __name__ == '__main__':
    app.run(debug=True)
