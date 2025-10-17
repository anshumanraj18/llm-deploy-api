import os
import json
import base64
import tempfile
import subprocess
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)

GITHUB_USER = os.getenv("GITHUB_USER")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SHARED_SECRET = os.getenv("SHARED_SECRET")
GIT_EMAIL = os.getenv("GIT_EMAIL")

def save_data_uri(uri, path):
    head, data = uri.split(",", 1)
    content = base64.b64decode(data)
    with open(path, "wb") as f:
        f.write(content)

def create_repo_structure(task, brief, attachments):
    tempdir = tempfile.mkdtemp(prefix=f"{task}-")
    index = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{task}</title></head>
<body>
  <h1>{task}</h1>
  <p>Brief: {brief}</p>
</body>
</html>"""
    with open(f"{tempdir}/index.html", "w") as f:
        f.write(index)

    with open(f"{tempdir}/README.md", "w") as f:
        f.write(f"# {task}\n\nAuto-generated app\n\n## Brief\n{brief}\n")

    with open(f"{tempdir}/LICENSE", "w") as f:
        f.write("MIT License\n\nCopyright (c) 2025\n")

    for att in attachments:
        name, uri = att["name"], att["url"]
        save_data_uri(uri, f"{tempdir}/{name}")

    return tempdir

def git_push(local_dir, repo_name):
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{repo_name}.git"
    cmds = [
        ["git", "init"],
        ["git", "config", "user.name", GITHUB_USER],
        ["git", "config", "user.email", GIT_EMAIL],
        ["git", "add", "."],
        ["git", "commit", "-m", "initial commit"],
        ["git", "branch", "-M", "main"],
        ["git", "remote", "add", "origin", repo_url],
        ["git", "push", "-u", "origin", "main"]
    ]
    for cmd in cmds:
        subprocess.run(cmd, cwd=local_dir, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=local_dir).decode().strip()
    return sha

@app.route("/api-endpoint", methods=["POST"])
def api_endpoint():
    data = request.get_json(force=True)
    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Invalid secret"}), 403

    email = data["email"]
    task = data["task"]
    brief = data["brief"]
    round_ = data["round"]
    nonce = data["nonce"]
    evaluation_url = data["evaluation_url"]
    attachments = data.get("attachments", [])

    repo_name = task.replace("_", "-")
    local_dir = create_repo_structure(task, brief, attachments)

    # Create repo via GitHub API
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.post("https://api.github.com/user/repos", headers=headers,
                      json={"name": repo_name, "private": False})
    if r.status_code not in [201, 422]:
        return jsonify({"error": "Failed to create GitHub repo"}), 500

    commit_sha = git_push(local_dir, repo_name)
    pages_url = f"https://{GITHUB_USER}.github.io/{repo_name}/"

    # Send evaluation callback
    payload = {
        "email": email,
        "task": task,
        "round": round_,
        "nonce": nonce,
        "repo_url": f"https://github.com/{GITHUB_USER}/{repo_name}",
        "commit_sha": commit_sha,
        "pages_url": pages_url
    }
    requests.post(evaluation_url, json=payload, headers={"Content-Type": "application/json"})

    return jsonify({"status": "ok", "repo": payload}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
