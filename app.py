from flask import Flask
from pr_nudge import build_message, fetch_prs, filter_stale
from config import load_config
import requests

app = Flask(__name__)

@app.route('/stale-prs', methods=['GET'])
def stale_prs_route():
    config = load_config()
    
    session = requests.Session()
    session.headers['Authorization'] = f"token {config['github_token']}"
    
    prs = fetch_prs(session, config['github_repo'], config.get('github_user'))
    stale_prs = filter_stale(prs, config['stale_days'], config.get('exclude_labels', []))
    message = build_message(stale_prs)
    
    return message

if __name__ == '__main__':
    app.run(debug=True)
