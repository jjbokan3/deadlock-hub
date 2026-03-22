#!/usr/bin/env python3
"""Dev dashboard for managing the Deadlock patch notes pipeline.

Provides a web UI for:
  - Viewing service status (server, watcher, dashboard)
  - Tailing logs in real time
  - Cache and generated file management
  - Manual RSS polling
  - Deploying latest code to prod

Binds to 127.0.0.1 only — not publicly accessible.

Usage:
    python dashboard.py                  # default port 8087
    python dashboard.py --port 8087
"""
from __future__ import annotations
import argparse
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dashboard")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
CACHE_DIR = os.path.join(PROJECT_DIR, ".cache")
UPDATES_DIR = os.path.join(PROJECT_DIR, "site", "deadlock", "updates")

SERVICES = {
    "server": "io.josephbokan.deadlock-server",
    "watcher": "io.josephbokan.deadlock-watcher",
    "dashboard": "io.josephbokan.deadlock-dashboard",
}


def _get_uid() -> int:
    return os.getuid()


def _service_status() -> list[dict]:
    """Get status of all launchd services."""
    results = []
    for label, plist_id in SERVICES.items():
        info = {"name": label, "id": plist_id, "running": False, "pid": None}
        try:
            out = subprocess.run(
                ["launchctl", "print", f"gui/{_get_uid()}/{plist_id}"],
                capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0:
                info["running"] = True
                for line in out.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("pid ="):
                        pid_str = line.split("=")[1].strip()
                        if pid_str.isdigit():
                            info["pid"] = int(pid_str)
        except Exception:
            pass
        results.append(info)
    return results


def _read_log(service: str, lines: int = 100) -> str:
    """Read last N lines of a service log."""
    log_file = os.path.join(LOGS_DIR, f"{service}.log")
    if not os.path.exists(log_file):
        return f"Log file not found: {log_file}"
    try:
        result = subprocess.run(
            ["tail", f"-{lines}", log_file],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except Exception as e:
        return f"Error reading log: {e}"


def _clear_api_cache() -> str:
    """Clear heroes/items API cache."""
    cleared = []
    for fname in ["heroes.json", "items.json"]:
        path = os.path.join(CACHE_DIR, fname)
        if os.path.exists(path):
            os.remove(path)
            cleared.append(fname)
    return f"Cleared: {', '.join(cleared)}" if cleared else "No API cache files found"


def _clear_seen_patches() -> str:
    """Clear seen patches cache (will reprocess on next poll)."""
    path = os.path.join(CACHE_DIR, "seen_patches.json")
    if os.path.exists(path):
        os.remove(path)
        return "Cleared seen_patches.json"
    return "No seen patches cache found"


def _clear_generated() -> str:
    """Clear all generated patch files and regenerate index."""
    count = 0
    if os.path.isdir(UPDATES_DIR):
        for f in os.listdir(UPDATES_DIR):
            if f != "index.html":
                path = os.path.join(UPDATES_DIR, f)
                if os.path.isfile(path):
                    os.remove(path)
                    count += 1
    # Regenerate empty index
    try:
        sys.path.insert(0, PROJECT_DIR)
        from index_generator import write_index
        write_index(UPDATES_DIR)
    except Exception as e:
        return f"Cleared {count} files, but failed to regenerate index: {e}"
    return f"Cleared {count} files and regenerated index"


def _manual_poll(llm: str = "heuristic") -> str:
    """Run watcher.py --once and return output."""
    cmd = [
        sys.executable, os.path.join(PROJECT_DIR, "watcher.py"),
        "--once", "--llm", llm,
        "--output-dir", UPDATES_DIR,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=PROJECT_DIR,
        )
        output = result.stderr + result.stdout
        return output if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Timed out after 5 minutes"
    except Exception as e:
        return f"Error: {e}"


def _restart_service(name: str) -> str:
    """Restart a launchd service."""
    plist_id = SERVICES.get(name)
    if not plist_id:
        return f"Unknown service: {name}"
    try:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{_get_uid()}/{plist_id}"],
            capture_output=True, text=True, timeout=10
        )
        return f"Restarted {name}"
    except Exception as e:
        return f"Failed to restart {name}: {e}"


def _deploy() -> str:
    """Run deploy.sh to pull latest code and restart services."""
    script = os.path.join(PROJECT_DIR, "deploy.sh")
    if not os.path.exists(script):
        return "deploy.sh not found"
    try:
        result = subprocess.run(
            ["bash", script],
            capture_output=True, text=True, timeout=300,
            cwd=PROJECT_DIR,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "Deploy timed out after 5 minutes"
    except Exception as e:
        return f"Deploy error: {e}"


def _regenerate() -> str:
    """Clear seen cache and regenerate all patch pages."""
    seen = os.path.join(CACHE_DIR, "seen_patches.json")
    if os.path.exists(seen):
        os.remove(seen)
    return _manual_poll("heuristic")


def _git_info() -> dict:
    """Get current git commit info."""
    info = {"commit": "unknown", "date": "unknown", "branch": "unknown", "behind": 0}
    try:
        info["commit"] = subprocess.run(
            ["git", "log", "-1", "--format=%h"], capture_output=True, text=True,
            cwd=PROJECT_DIR, timeout=5
        ).stdout.strip()
        info["date"] = subprocess.run(
            ["git", "log", "-1", "--format=%ci"], capture_output=True, text=True,
            cwd=PROJECT_DIR, timeout=5
        ).stdout.strip()
        info["branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True,
            cwd=PROJECT_DIR, timeout=5
        ).stdout.strip()
        subprocess.run(
            ["git", "fetch", "--quiet"], capture_output=True, text=True,
            cwd=PROJECT_DIR, timeout=15
        )
        behind = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, cwd=PROJECT_DIR, timeout=5
        ).stdout.strip()
        info["behind"] = int(behind) if behind.isdigit() else 0
    except Exception:
        pass
    return info


def _cache_info() -> dict:
    """Get info about cache files."""
    info = {"api_cache": [], "seen_patches": None, "generated_files": 0}
    for fname in ["heroes.json", "items.json"]:
        path = os.path.join(CACHE_DIR, fname)
        if os.path.exists(path):
            import time
            age = time.time() - os.path.getmtime(path)
            info["api_cache"].append({"file": fname, "age_min": round(age / 60)})
    seen_path = os.path.join(CACHE_DIR, "seen_patches.json")
    if os.path.exists(seen_path):
        try:
            with open(seen_path) as f:
                info["seen_patches"] = len(json.load(f))
        except Exception:
            info["seen_patches"] = -1
    if os.path.isdir(UPDATES_DIR):
        info["generated_files"] = len([
            f for f in os.listdir(UPDATES_DIR)
            if f.endswith(".html") and f != "index.html"
        ])
    return info


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for the dashboard."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._send_html(DASHBOARD_HTML)
        elif path == "/api/status":
            data = {
                "services": _service_status(),
                "git": _git_info(),
                "cache": _cache_info(),
            }
            self._send_json(data)
        elif path == "/api/logs":
            service = params.get("service", ["watcher"])[0]
            lines = int(params.get("lines", ["200"])[0])
            if service not in ("server", "watcher", "dashboard"):
                self._send_json({"error": "invalid service"}, 400)
                return
            self._send_json({"service": service, "lines": _read_log(service, lines)})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/poll":
            llm = params.get("llm", ["heuristic"])[0]
            result = _manual_poll(llm)
            self._send_json({"success": True, "output": result})
        elif path == "/api/cache/clear":
            self._send_json({"success": True, "message": _clear_api_cache()})
        elif path == "/api/cache/clear-seen":
            self._send_json({"success": True, "message": _clear_seen_patches()})
        elif path == "/api/generated/clear":
            self._send_json({"success": True, "message": _clear_generated()})
        elif path == "/api/service/restart":
            name = params.get("name", [""])[0]
            self._send_json({"success": True, "message": _restart_service(name)})
        elif path == "/api/deploy":
            self._send_json({"success": True, "output": _deploy()})
        elif path == "/api/regenerate":
            self._send_json({"success": True, "output": _regenerate()})
        else:
            self._send_json({"error": "not found"}, 404)

    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deadlock Patch Tool — Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Chakra+Petch:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#0a0b0f;--bg-card:#12141c;--bg-hover:#181b26;
    --border:#252a38;--text:#e8eaf0;--dim:#8b90a5;--faint:#565b72;
    --accent:#ff6b2c;--accent-dim:#ff6b2c25;
    --green:#4ade80;--red:#f87171;--yellow:#fbbf24;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--text);font-family:'Chakra Petch',sans-serif;min-height:100vh;padding:32px}
  .container{max-width:1100px;margin:0 auto}
  h1{font-family:'Rajdhani',sans-serif;font-size:36px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
  .subtitle{color:var(--dim);font-size:14px;margin-bottom:32px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
  .card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px}
  .card h2{font-family:'Rajdhani',sans-serif;font-size:18px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:14px;color:var(--dim)}
  .full{grid-column:1/-1}
  .status-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #ffffff08}
  .status-row:last-child{border:none}
  .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
  .dot.on{background:var(--green);box-shadow:0 0 8px #4ade8060}
  .dot.off{background:var(--red);box-shadow:0 0 8px #f8717160}
  .svc-name{font-family:'JetBrains Mono',monospace;font-size:13px;flex:1}
  .svc-pid{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--faint)}
  .btn{font-family:'Chakra Petch',sans-serif;font-size:13px;color:var(--accent);background:var(--accent-dim);border:1px solid #ff6b2c40;padding:7px 16px;border-radius:6px;cursor:pointer;transition:all 0.2s;white-space:nowrap}
  .btn:hover{background:#ff6b2c22;border-color:var(--accent)}
  .btn:disabled{opacity:0.4;cursor:not-allowed}
  .btn.danger{color:var(--red);background:#f8717115;border-color:#f8717140}
  .btn.danger:hover{background:#f8717125;border-color:var(--red)}
  .btn.green{color:var(--green);background:#4ade8015;border-color:#4ade8040}
  .btn.green:hover{background:#4ade8025;border-color:var(--green)}
  .btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
  .info-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--dim)}
  .info-val{color:var(--text)}
  .log-box{background:#08090c;border:1px solid var(--border);border-radius:8px;padding:14px;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.6;color:var(--dim);max-height:400px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;margin-top:10px}
  .log-tabs{display:flex;gap:6px;margin-bottom:10px}
  .log-tab{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--faint);background:none;border:1px solid transparent;padding:5px 12px;border-radius:5px;cursor:pointer}
  .log-tab.active{color:var(--accent);border-color:#ff6b2c40;background:var(--accent-dim)}
  .toast{position:fixed;bottom:24px;right:24px;background:var(--bg-card);border:1px solid var(--border);padding:12px 20px;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);opacity:0;transition:opacity 0.3s;pointer-events:none;z-index:100}
  .toast.show{opacity:1}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--faint);border-top-color:var(--accent);border-radius:50%;animation:spin 0.6s linear infinite;margin-right:6px;vertical-align:middle}
  @keyframes spin{to{transform:rotate(360deg)}}
  .behind-badge{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--yellow);background:#fbbf2415;border:1px solid #fbbf2440;padding:2px 8px;border-radius:4px;margin-left:8px}
  @media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
  <h1>Dashboard</h1>
  <p class="subtitle">Deadlock Patch Tool &mdash; localhost:8087</p>

  <div class="grid">
    <!-- Services -->
    <div class="card">
      <h2>Services</h2>
      <div id="services">Loading...</div>
    </div>

    <!-- Git / Deploy -->
    <div class="card">
      <h2>Deploy</h2>
      <div id="git-info">Loading...</div>
      <div class="btn-row">
        <button class="btn green" onclick="deploy()">Pull &amp; Restart</button>
        <button class="btn" onclick="regenerate()">Regenerate Pages</button>
      </div>
    </div>

    <!-- Cache -->
    <div class="card">
      <h2>Cache</h2>
      <div id="cache-info">Loading...</div>
      <div class="btn-row">
        <button class="btn" onclick="apiPost('/api/cache/clear')">Clear API Cache</button>
        <button class="btn danger" onclick="apiPost('/api/cache/clear-seen')">Clear Seen Patches</button>
        <button class="btn danger" onclick="apiPost('/api/generated/clear')">Clear Generated</button>
      </div>
    </div>

    <!-- Manual Poll -->
    <div class="card">
      <h2>Manual Poll</h2>
      <p style="font-size:13px;color:var(--dim);margin-bottom:10px">Trigger an RSS check and process new patches.</p>
      <div class="btn-row">
        <button class="btn" id="poll-btn" onclick="manualPoll('heuristic')">Poll (Heuristic)</button>
        <button class="btn" id="poll-claude-btn" onclick="manualPoll('claude')">Poll (Claude)</button>
      </div>
      <div id="poll-output" class="log-box" style="display:none;max-height:250px"></div>
    </div>

    <!-- Logs -->
    <div class="card full">
      <h2>Logs</h2>
      <div class="log-tabs">
        <button class="log-tab active" onclick="switchLog('watcher',this)">Watcher</button>
        <button class="log-tab" onclick="switchLog('server',this)">Server</button>
        <button class="log-tab" onclick="switchLog('dashboard',this)">Dashboard</button>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
        <button class="btn" onclick="refreshLogs()">Refresh</button>
        <label style="font-size:12px;color:var(--faint);display:flex;align-items:center;gap:4px">
          <input type="checkbox" id="auto-follow" checked> Auto-refresh
        </label>
      </div>
      <div id="log-box" class="log-box">Loading logs...</div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let currentLogService = 'watcher';
let logTimer = null;

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  return res.json();
}

async function apiPost(url) {
  const data = await fetchJson(url, {method:'POST'});
  toast(data.message || data.output || 'Done');
  refreshStatus();
}

async function refreshStatus() {
  try {
    const data = await fetchJson('/api/status');
    // Services
    let shtml = '';
    data.services.forEach(s => {
      const dot = s.running ? 'on' : 'off';
      const pid = s.pid ? `PID ${s.pid}` : 'stopped';
      const restartBtn = `<button class="btn" style="padding:4px 10px;font-size:11px" onclick="apiPost('/api/service/restart?name=${s.name}')">restart</button>`;
      shtml += `<div class="status-row"><span class="dot ${dot}"></span><span class="svc-name">${s.name}</span><span class="svc-pid">${pid}</span>${restartBtn}</div>`;
    });
    document.getElementById('services').innerHTML = shtml;

    // Git
    const g = data.git;
    const behindBadge = g.behind > 0 ? `<span class="behind-badge">${g.behind} behind</span>` : '';
    document.getElementById('git-info').innerHTML = `
      <div class="info-row"><span>Branch</span><span class="info-val">${g.branch}${behindBadge}</span></div>
      <div class="info-row"><span>Commit</span><span class="info-val">${g.commit}</span></div>
      <div class="info-row"><span>Date</span><span class="info-val">${g.date}</span></div>
    `;

    // Cache
    const c = data.cache;
    let chtml = '';
    c.api_cache.forEach(f => {
      chtml += `<div class="info-row"><span>${f.file}</span><span class="info-val">${f.age_min}m old</span></div>`;
    });
    if (c.api_cache.length === 0) chtml += `<div class="info-row"><span>API cache</span><span class="info-val">empty</span></div>`;
    chtml += `<div class="info-row"><span>Seen patches</span><span class="info-val">${c.seen_patches !== null ? c.seen_patches : 'none'}</span></div>`;
    chtml += `<div class="info-row"><span>Generated pages</span><span class="info-val">${c.generated_files}</span></div>`;
    document.getElementById('cache-info').innerHTML = chtml;
  } catch(e) {
    console.error('Status fetch error:', e);
  }
}

async function refreshLogs() {
  try {
    const data = await fetchJson(`/api/logs?service=${currentLogService}&lines=200`);
    const box = document.getElementById('log-box');
    box.textContent = data.lines || '(empty)';
    box.scrollTop = box.scrollHeight;
  } catch(e) {
    document.getElementById('log-box').textContent = 'Error loading logs';
  }
}

function switchLog(service, btn) {
  currentLogService = service;
  document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  refreshLogs();
}

async function manualPoll(llm) {
  const btn = document.getElementById(llm === 'claude' ? 'poll-claude-btn' : 'poll-btn');
  const origText = btn.textContent;
  btn.innerHTML = '<span class="spinner"></span>Polling...';
  btn.disabled = true;
  const out = document.getElementById('poll-output');
  out.style.display = 'block';
  out.textContent = 'Running...';
  try {
    const data = await fetchJson(`/api/poll?llm=${llm}`, {method:'POST'});
    out.textContent = data.output || '(no output)';
    toast('Poll complete');
    refreshStatus();
  } catch(e) {
    out.textContent = 'Error: ' + e.message;
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
  }
}

async function deploy() {
  const out = document.getElementById('poll-output');
  out.style.display = 'block';
  out.textContent = 'Deploying (pull + regenerate + restart)...';
  try {
    const data = await fetchJson('/api/deploy', {method:'POST'});
    out.textContent = data.output || '(no output)';
    toast('Deploy complete');
    refreshStatus();
  } catch(e) {
    out.textContent = 'Error: ' + e.message;
  }
}

async function regenerate() {
  const out = document.getElementById('poll-output');
  out.style.display = 'block';
  out.textContent = 'Regenerating all patch pages...';
  try {
    const data = await fetchJson('/api/regenerate', {method:'POST'});
    out.textContent = data.output || '(no output)';
    toast('Regeneration complete');
    refreshStatus();
  } catch(e) {
    out.textContent = 'Error: ' + e.message;
  }
}

// Init
refreshStatus();
refreshLogs();

// Auto-refresh logs every 5s
setInterval(() => {
  if (document.getElementById('auto-follow').checked) refreshLogs();
}, 5000);

// Refresh status every 30s
setInterval(refreshStatus, 30000);
</script>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(description="Deadlock Patch Tool Dashboard")
    parser.add_argument("--port", type=int, default=8087, help="Port (default: 8087)")
    args = parser.parse_args()

    os.makedirs(LOGS_DIR, exist_ok=True)

    class ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True

    server = ReusableHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    logger.info(f"Dashboard running at http://localhost:{args.port}/")
    logger.info("Bound to 127.0.0.1 only (not publicly accessible)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
