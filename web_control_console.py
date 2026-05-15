#!/usr/bin/env python3
"""Browser-based local-development console for ME470.

This fallback console avoids Qt entirely. It is useful on lab machines where
the PySide6/macOS platform plugin stack is fussy, while still calling the same
app_core service layer and current algorithm modules.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import sys


ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "主程序代码"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app_core import ControlConsoleService  # noqa: E402


HOST = "127.0.0.1"
PORT = 8765
SERVICE = ControlConsoleService()


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ME470 Control Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f7;
      --panel: #ffffff;
      --line: #d5dbe1;
      --text: #17202a;
      --muted: #667381;
      --accent: #2364aa;
      --ok: #177245;
      --bad: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    header {
      padding: 18px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { margin: 0; font-size: 20px; letter-spacing: 0; }
    main { padding: 18px 24px 28px; max-width: 1400px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }
    .span-4 { grid-column: span 4; }
    .span-6 { grid-column: span 6; }
    .span-8 { grid-column: span 8; }
    .span-12 { grid-column: span 12; }
    h2 { margin: 0 0 10px; font-size: 15px; }
    button {
      border: 1px solid #aeb7c1;
      background: #fff;
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); background: #eef5ff; }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
    }
    label { color: var(--muted); display: block; margin: 8px 0 4px; }
    pre {
      margin: 0;
      background: #fbfcfd;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      overflow: auto;
      max-height: 420px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 7px; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .status { color: var(--muted); }
    .ok { color: var(--ok); }
    .bad { color: var(--bad); }
    .images { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .images img { width: 100%; max-height: 320px; object-fit: contain; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
    @media (max-width: 900px) { .span-4, .span-6, .span-8 { grid-column: span 12; } .images { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>ME470 Control Console</h1>
    <div class="row">
      <span id="status" class="status">Ready</span>
      <button onclick="refreshAll()">Refresh</button>
    </div>
  </header>
  <main class="grid">
    <section class="panel span-4">
      <h2>Dashboard</h2>
      <pre id="dashboard">Loading...</pre>
    </section>
    <section class="panel span-4">
      <h2>Target Sequence Dry-Run</h2>
      <label>Pick X Y Z</label>
      <input id="pick" value="220 0 115">
      <label>Place X Y Z</label>
      <input id="place" value="0 250 124.25">
      <p><button onclick="targetDryRun()">Generate Target Sequence</button></p>
      <pre id="targetResult">No target dry-run from this page yet.</pre>
    </section>
    <section class="panel span-4">
      <h2>Auto Demo</h2>
      <p class="status">Dry-run only. Hardware sending stays in the existing CLI for now.</p>
      <button onclick="detectedDryRun()">Dry-Run Detected Books Loop</button>
      <pre id="autoResult">No auto-demo run from this page yet.</pre>
    </section>
    <section class="panel span-6">
      <h2>Decision</h2>
      <div id="tasks"></div>
    </section>
    <section class="panel span-6">
      <h2>Latest Report</h2>
      <pre id="report"></pre>
    </section>
    <section class="panel span-6">
      <h2>Commands</h2>
      <pre id="commands"></pre>
    </section>
    <section class="panel span-6">
      <h2>Summary</h2>
      <pre id="summary"></pre>
    </section>
    <section class="panel span-12">
      <h2>Visual Overlays</h2>
      <div id="images" class="images"></div>
    </section>
    <section class="panel span-12">
      <h2>Parameters</h2>
      <pre id="params"></pre>
    </section>
  </main>
  <script>
    async function api(path, options = {}) {
      const res = await fetch(path, options);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }
    function setStatus(text, cls = "status") {
      const el = document.getElementById("status");
      el.className = cls;
      el.textContent = text;
    }
    function text(id, value) {
      document.getElementById(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }
    function renderTasks(snapshot) {
      const tasks = snapshot.tasks || [];
      if (!tasks.length) {
        document.getElementById("tasks").innerHTML = "<p class='status'>No latest detected-books tasks found.</p>";
        return;
      }
      const rows = tasks.map(t => `<tr><td>${t.index ?? ""}</td><td>${t.title ?? ""}</td><td>${fmtVec(t.pick)}</td><td>${fmtVec(t.place)}</td><td>${t.command_count ?? ""}</td></tr>`).join("");
      document.getElementById("tasks").innerHTML = `<table><thead><tr><th>#</th><th>Title</th><th>Pick</th><th>Place</th><th>Commands</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    function renderImages(paths) {
      const html = paths.length ? paths.map(p => `<figure><img src="/file?path=${encodeURIComponent(p)}"><figcaption>${p}</figcaption></figure>`).join("") : "<p class='status'>No overlays found yet.</p>";
      document.getElementById("images").innerHTML = html;
    }
    function fmtVec(v) {
      return Array.isArray(v) && v.length === 3 ? `(${v.map(x => Number(x).toFixed(1)).join(", ")})` : "";
    }
    async function refreshAll() {
      setStatus("Refreshing...");
      try {
        const data = await api("/api/state");
        text("dashboard", data.status);
        text("params", data.parameters);
        text("report", data.report);
        text("commands", data.commands);
        text("summary", data.summary);
        renderTasks(data.snapshot || {});
        renderImages(data.visual_paths || []);
        setStatus("Ready", "ok");
      } catch (err) {
        setStatus(String(err), "bad");
      }
    }
    async function targetDryRun() {
      setStatus("Generating target sequence...");
      const body = new URLSearchParams({ pick: document.getElementById("pick").value, place: document.getElementById("place").value });
      const result = await api("/api/target-dry", { method: "POST", body });
      text("targetResult", result);
      await refreshAll();
    }
    async function detectedDryRun() {
      setStatus("Preparing auto-demo dry-run...");
      const result = await api("/api/detected-dry", { method: "POST" });
      text("autoResult", result);
      await refreshAll();
    }
    refreshAll();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/api/state":
            self._send_json(self._state())
            return
        if parsed.path == "/file":
            query = parse_qs(parsed.query)
            path = Path(query.get("path", [""])[0])
            self._send_file(path)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        if parsed.path == "/api/target-dry":
            result = SERVICE.run_target_sequence_dry(
                pick=_parse_vec3(form.get("pick", [""])[0]),
                place=_parse_vec3(form.get("place", [""])[0]),
            )
            self._send_json(_operation_payload(result))
            return
        if parsed.path == "/api/detected-dry":
            result = SERVICE.prepare_detected_books_run(dry_run=True)
            self._send_json(_operation_payload(result))
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[WEB] {self.address_string()} - {fmt % args}")

    def _state(self) -> dict[str, object]:
        return {
            "status": SERVICE.project_status(),
            "parameters": SERVICE.parameter_snapshot(),
            "snapshot": SERVICE.latest_snapshot(),
            "report": SERVICE.latest_decision_report(),
            "commands": SERVICE.latest_command_text(),
            "summary": SERVICE.latest_summary_text(),
            "visual_paths": [str(path) for path in SERVICE.latest_visual_paths()],
        }

    def _send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, value: str) -> None:
        payload = value.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(ROOT.resolve())
        except Exception:
            self.send_error(403)
            return
        if not resolved.exists() or not resolved.is_file():
            self.send_error(404)
            return
        payload = resolved.read_bytes()
        self.send_response(200)
        self.send_header("content-type", _content_type(resolved))
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _operation_payload(result) -> dict[str, object]:
    return {
        "ok": result.ok,
        "message": result.message,
        "payload": result.payload,
        "stdout": result.stdout,
    }


def _parse_vec3(text: str) -> tuple[float, float, float]:
    parts = text.replace(",", " ").split()
    if len(parts) != 3:
        raise ValueError("expected exactly three numbers: X Y Z")
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".png"}:
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ME470 Web Control Console: http://{HOST}:{PORT}")
    print("Press Ctrl+C here to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ME470 Web Control Console.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
