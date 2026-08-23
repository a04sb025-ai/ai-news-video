#!/usr/bin/env python3
"""Bounded GitHub Actions monitor; workflow failure is a terminal result."""
import argparse, json, re, subprocess, time

TERMINAL = {"success", "failure", "cancelled", "timed_out", "action_required", "neutral", "skipped", "stale"}

def view(run):
    process = subprocess.run(["gh", "run", "view", run, "--json", "name,url,status,conclusion,jobs"], text=True, capture_output=True, timeout=30)
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or "gh run view failed")
    return json.loads(process.stdout)

def artifacts_available(run):
    match = re.search(r"github\.com/([^/]+/[^/]+)/actions/runs/(\d+)", run)
    if match:
        endpoint = f"repos/{match.group(1)}/actions/runs/{match.group(2)}/artifacts"
    else:
        endpoint = f"repos/{{owner}}/{{repo}}/actions/runs/{run}/artifacts"
    process = subprocess.run(["gh", "api", endpoint, "--jq", ".total_count"], text=True, capture_output=True, timeout=30)
    return process.returncode == 0 and int(process.stdout.strip() or 0) > 0

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("run", help="GitHub run ID or URL")
    parser.add_argument("--timeout", type=int, default=600); parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args(); deadline = time.monotonic() + args.timeout
    attempts = max(1, args.timeout // max(1, args.interval) + 1)
    for _ in range(attempts):
        data = view(args.run); conclusion = (data.get("conclusion") or "").lower(); status = (data.get("status") or "").lower()
        if status == "completed" or conclusion in TERMINAL:
            failures = TERMINAL - {"success", "neutral", "skipped"}
            failed = [f"{job.get('name')}: {step.get('name')}" for job in data.get("jobs", []) for step in job.get("steps", []) if step.get("conclusion") in failures]
            summary = {"workflow_name": data.get("name"), "run_url": data.get("url"), "status": status, "conclusion": conclusion or None,
                       "failed_steps": failed, "artifacts_available": artifacts_available(args.run)}
            print("GitHub Actions completed"); print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if conclusion == "success" else 1
        if time.monotonic() + args.interval > deadline: break
        time.sleep(args.interval)
    print("Workflow is still running after timeout.\nStopping monitoring."); return 2

if __name__ == "__main__": raise SystemExit(main())
