#!/usr/bin/env python3
"""
Generate a static HTML dashboard from selector_output.json.

Usage (from repo root or tools/):
  python tools/generate_dashboard.py --input selector_output.json --outdir tools/output/dashboard

The output directory will contain:
  - index.html                A single-file dashboard (self-contained CSS/JS)
  - selector_output.json      Original JSON copied for reference/download

No external dependencies required (Python 3.8+).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Tuple


def _default_input_path(script_path: Path) -> Path:
    # Assume repo structure where selector_output.json lives at repo root
    repo_root = script_path.resolve().parents[1]  # tools/ -> repo root
    return repo_root / "selector_output.json"


def _parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    parser = argparse.ArgumentParser(description="Generate static dashboard for selector_output.json")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=_default_input_path(script_path),
        help="Path to selector_output.json (default: repo_root/selector_output.json)",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        type=Path,
        default=script_path.parent / "output" / "dashboard",
        help="Output directory to write the dashboard (default: tools/output/dashboard)",
    )
    return parser.parse_args()


def _safe_get(d: Dict[str, Any], key: str, default: Any) -> Any:
    try:
        v = d.get(key, default)
        return v if v is not None else default
    except Exception:
        return default


def _split_test_id(test_id: str) -> Tuple[str, str, str]:
    """Split FullyQualifiedClass#method into (package, class, method)."""
    if not test_id:
        return ("", "", "")
    parts = test_id.split("#", 1)
    class_fq = parts[0]
    method = parts[1] if len(parts) > 1 else ""
    pkg_parts = class_fq.rsplit(".", 1)
    if len(pkg_parts) == 2:
        pkg, clazz = pkg_parts
    else:
        pkg, clazz = "", class_fq
    return (pkg, clazz, method)


def _group_tests(selected_tests: List[str]) -> Dict[str, List[Tuple[str, str]]]:
    """Group tests by class. Returns {class_fq: [(method, test_id), ...]} sorted by method."""
    groups: Dict[str, List[Tuple[str, str]]] = {}
    for tid in selected_tests:
        class_fq, method = (tid.split("#", 1) + [""])[:2]
        groups.setdefault(class_fq, []).append((method, tid))
    # sort methods
    for k in list(groups.keys()):
        groups[k] = sorted(groups[k], key=lambda x: (x[0], x[1]))
    return dict(sorted(groups.items(), key=lambda x: x[0]))


def _html_escape(s: Any) -> str:
    from html import escape

    return escape(str(s), quote=True)


def _human_ts() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")


def _render_html(data: Dict[str, Any]) -> str:
    selected_tests: List[str] = _safe_get(data, "selected_tests", []) or []
    explanations: Dict[str, Any] = _safe_get(data, "explanations", {}) or {}
    confidence: float = _safe_get(data, "confidence", None)
    metadata: Dict[str, Any] = _safe_get(data, "metadata", {}) or {}

    # Any additional top-level fields (besides the known ones)
    known_keys = {"selected_tests", "explanations", "confidence", "metadata"}
    extras = {k: v for k, v in data.items() if k not in known_keys}

    total_tests = len(selected_tests)
    grouped = _group_tests(selected_tests)

    confidence_pct = None
    try:
        if isinstance(confidence, (int, float)):
            confidence_pct = max(0.0, min(1.0, float(confidence))) * 100.0
    except Exception:
        confidence_pct = None

    # Prettified JSON blobs
    metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
    extras_json = json.dumps(extras, indent=2, ensure_ascii=False)
    raw_json = json.dumps(data, indent=2, ensure_ascii=False)

    # Inline CSS and JS for a single-file artifact
    css = """
    /* Design tokens: dark default, light override via prefers-color-scheme */
    :root {
      --bg: #0b1020;          /* deep slate */
      --panel: #0f172a;       /* slate-900 */
      --panel-2: #111827;     /* gray-900 */
      --card: #0d1426;        /* card bg */
      --text: #e6e8ec;        /* text */
      --muted: #98a2b3;       /* muted text */
      --border: #1f2937;      /* border */
      --code: #0b1220;        /* code bg */
      --accent: #60a5fa;      /* blue-400 */
      --accent-2: #34d399;    /* emerald-400 */
      --row-hover: rgba(96,165,250,0.08);
      --row-zebra: rgba(148,163,184,0.08);
      --focus: rgba(96,165,250,0.45);
      --shadow: 0 1px 2px rgba(0,0,0,0.2), 0 6px 12px rgba(0,0,0,0.12);
    }

    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f8fafc;        /* slate-50 */
        --panel: #ffffff;
        --panel-2: #f1f5f9;    /* slate-100 */
        --card: #ffffff;
        --text: #0f172a;       /* slate-900 */
        --muted: #475569;      /* slate-600 */
        --border: #e2e8f0;     /* slate-200 */
        --code: #0b1220;
        --row-hover: rgba(2,132,199,0.08);
        --row-zebra: rgba(148,163,184,0.18);
        --focus: rgba(59,130,246,0.45);
        --shadow: 0 1px 2px rgba(0,0,0,0.06), 0 8px 20px rgba(0,0,0,0.08);
      }
    }

    * { box-sizing: border-box; }
    html, body {
      margin: 0; padding: 0;
      background: var(--bg); color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      line-height: 1.5;
      -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .container { max-width: 1200px; margin: 0 auto; padding: 28px 20px; }
    .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; gap: 12px; }
    .title { font-size: 22px; font-weight: 800; letter-spacing: 0.2px; }
    .subtitle { color: var(--muted); font-size: 12px; }

    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px; box-shadow: var(--shadow);
    }
    .card h3 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
    .metric { font-size: 30px; font-weight: 800; letter-spacing: -0.02em; }

    .progress { background: var(--panel-2); border: 1px solid var(--border); height: 10px; border-radius: 999px; overflow: hidden; }
    .bar { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); width: 0%; transition: width 600ms ease; }

    .section { margin-top: 28px; }
    .section h2 { font-size: 18px; margin: 0 0 12px; letter-spacing: 0.2px; }
    .muted { color: var(--muted); }

    .search {
      width: 100%; padding: 12px 14px; border-radius: 10px;
      border: 1px solid var(--border); background: var(--panel); color: var(--text);
      outline: none; transition: box-shadow .2s ease, border-color .2s ease;
    }
    .search:focus { box-shadow: 0 0 0 4px var(--focus); border-color: var(--accent); }

    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
    th { color: var(--muted); font-weight: 700; background: var(--panel-2); position: sticky; top: 0; z-index: 1; backdrop-filter: blur(2px); }
    tbody tr:nth-child(even) { background: var(--row-zebra); }
    tbody tr:hover { background: var(--row-hover); }

    details { border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; background: var(--panel); box-shadow: var(--shadow); }
    details + details { margin-top: 12px; }
    details[open] { padding-bottom: 16px; }
    summary { cursor: pointer; font-weight: 700; margin-bottom: 8px; }
    summary:hover { color: var(--accent); }

    .explanation-content { 
      margin-top: 8px; 
      padding: 12px; 
      background: var(--panel-2); 
      border-radius: 8px; 
      border: 1px solid var(--border);
    }
    .explanation-text {
      white-space: pre-wrap; 
      word-wrap: break-word; 
      overflow-wrap: break-word;
      max-width: 100%;
      line-height: 1.6;
    }

    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    pre { 
      background: var(--code); color: #e5e7eb; padding: 12px; border-radius: 10px; 
      overflow: auto; border: 1px solid var(--border); 
      white-space: pre-wrap; word-wrap: break-word; max-width: 100%;
    }

    .footer { margin-top: 30px; font-size: 12px; color: var(--muted); }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--panel-2); border: 1px solid var(--border); font-size: 12px; max-width: 480px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pill { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--panel); box-shadow: var(--shadow); }

    .row-actions { display: flex; gap: 8px; align-items: center; }
    .copy-btn { cursor: pointer; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); transition: background .15s ease, transform .05s ease, box-shadow .2s ease; }
    .copy-btn:hover { background: var(--panel-2); }
    .copy-btn:active { transform: translateY(1px); }
    .copy-btn:focus { outline: none; box-shadow: 0 0 0 4px var(--focus); border-color: var(--accent); }

    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .two-col { grid-template-columns: 1fr; } }
    """

    js = """
    // Simple interactivity
    const data = { raw: __RAW_JSON__ };
    function init() {
      const bar = document.querySelector('.bar');
      if (bar) {
        const pct = __CONFIDENCE_PCT__;
        if (pct !== null) bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
      }
      const filter = document.getElementById('test-filter');
      const rows = Array.from(document.querySelectorAll('#tests-body tr'));
      if (filter) {
        filter.addEventListener('input', () => {
          const q = filter.value.trim().toLowerCase();
          rows.forEach(tr => {
            const txt = tr.getAttribute('data-search') || '';
            tr.style.display = txt.includes(q) ? '' : 'none';
          });
        });
      }
      document.querySelectorAll('[data-copy]').forEach(btn => {
        btn.addEventListener('click', () => {
          const txt = btn.getAttribute('data-copy') || '';
          navigator.clipboard.writeText(txt).then(() => {
            btn.textContent = 'Copied';
            setTimeout(() => btn.textContent = 'Copy', 1000);
          }).catch(() => {});
        });
      });
    }
    document.addEventListener('DOMContentLoaded', init);
    """
    # Prevent </script> from prematurely closing the inline script
    raw_json_safe = raw_json.replace("</", "<\\/")
    js = js.replace("__RAW_JSON__", raw_json_safe)
    js = js.replace("__CONFIDENCE_PCT__", "null" if confidence_pct is None else f"{confidence_pct}")

    # Build tests table rows
    test_rows = []
    for class_fq, methods in grouped.items():
        pkg, clazz = (class_fq.rsplit(".", 1) + [class_fq])[-2:]
        for method, tid in methods:
            pkg2, clazz2, method2 = _split_test_id(tid)
            search_key = f"{class_fq} {method} {pkg2} {clazz2} {method2}".lower()
            test_rows.append(
                f"<tr data-search='{_html_escape(search_key)}'>"
                f"<td><code>{_html_escape(clazz2 or clazz)}</code></td>"
                f"<td><code>{_html_escape(method2 or method)}</code></td>"
                f"<td class='muted'>{_html_escape(pkg2)}</td>"
                f"<td><div class='row-actions'><button class='copy-btn' data-copy='{_html_escape(tid)}'>Copy</button><span class='badge'>{_html_escape(tid)}</span></div></td>"
                f"</tr>"
            )

    # Build explanations
    expl_blocks = []
    for k, v in sorted(explanations.items(), key=lambda x: str(x[0])):
        key_html = _html_escape(k)
        try:
            if isinstance(v, (dict, list)):
                content = json.dumps(v, indent=2, ensure_ascii=False)
                body = f"<div class='explanation-content'><pre class='explanation-text'>{_html_escape(content)}</pre></div>"
            else:
                content = str(v)
                body = f"<div class='explanation-content'><div class='explanation-text'>{_html_escape(content)}</div></div>"
        except Exception:
            content = str(v)
            body = f"<div class='explanation-content'><div class='explanation-text'>{_html_escape(content)}</div></div>"
        expl_blocks.append(f"<details open><summary>{key_html}</summary>{body}</details>")

    confidence_text = (
        f"{confidence:.3f} ({confidence_pct:.1f}% )" if confidence_pct is not None and isinstance(confidence, (int, float)) else("N/A")
    )

    # Pre-escape dynamic content to avoid f-string backslash issues
    title_html = _html_escape("DeltaTest — Selector Dashboard")
    timestamp_html = _html_escape(_human_ts())
    confidence_html = _html_escape(confidence_text)
    confidence_width = confidence_pct or 0
    metadata_html = _html_escape(metadata_json)
    extras_html = _html_escape(extras_json) if extras else ""
    raw_json_html = _html_escape(raw_json)
    tests_rows_html = ''.join(test_rows) if test_rows else '<tr><td colspan="4" class="muted">No tests selected</td></tr>'
    explanations_html = '\n'.join(expl_blocks) if expl_blocks else '<div class="muted">No explanations available</div>'
    extras_section = f'<div style="height:8px"></div><h2>Other fields</h2><pre>{extras_html}</pre>' if extras else ''

    # Compose the full HTML
    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>{title_html}</title>
      <style>{css}</style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div>
            <div class="title">{title_html}</div>
            <div class="subtitle">Static artifact generated on {timestamp_html}</div>
          </div>
          <div class="pill"><span>JSON:</span> <a href="selector_output.json" download>selector_output.json</a></div>
        </div>

        <div class="grid">
          <div class="card">
            <h3>Confidence</h3>
            <div class="metric">{confidence_html}</div>
            <div class="progress" aria-label="confidence">
              <div class="bar" style="width: {confidence_width:.1f}%"></div>
            </div>
          </div>
          <div class="card">
            <h3>Selected Tests</h3>
            <div class="metric">{total_tests}</div>
            <div class="muted">FullyQualifiedClass#method</div>
          </div>
          <div class="card">
            <h3>Groups (Classes)</h3>
            <div class="metric">{len(grouped)}</div>
            <div class="muted">Grouped by test class</div>
          </div>
        </div>

        <div class="section">
          <h2>Selected tests</h2>
          <input id="test-filter" class="search" placeholder="Filter by class, method, or package…" />
          <div style="height: 10px"></div>
          <div style="max-height: 480px; overflow: auto; border: 1px solid var(--border); border-radius: 10px;">
            <table>
              <thead>
                <tr><th>Class</th><th>Method</th><th>Package</th><th>Test Id</th></tr>
              </thead>
              <tbody id="tests-body">
                {tests_rows_html}
              </tbody>
            </table>
          </div>
        </div>

        <div class="section two-col">
          <div>
            <h2>Explanations</h2>
            {explanations_html}
          </div>
          <div>
            <h2>Metadata</h2>
            <pre>{metadata_html}</pre>
            {extras_section}
          </div>
        </div>

        <div class="section">
          <details>
            <summary>View raw selector_output.json</summary>
            <pre>{raw_json_html}</pre>
          </details>
        </div>

        <div class="footer">DeltaTest • Static dashboard • Generated {timestamp_html}</div>
      </div>
      <script>{js}</script>
    </body>
    </html>
    """
    return html


def main() -> int:
    args = _parse_args()
    input_path: Path = args.input
    outdir: Path = args.outdir

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 2
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Failed to create output directory {outdir}: {e}", file=sys.stderr)
        return 3

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"ERROR: Failed to read input: {e}", file=sys.stderr)
        return 5

    html = _render_html(data if isinstance(data, dict) else {"raw": data})

    index_path = outdir / "index.html"
    try:
        index_path.write_text(html, encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Failed to write HTML: {e}", file=sys.stderr)
        return 6

    # Copy JSON alongside for download/reference
    try:
        shutil.copy2(str(input_path), str(outdir / "selector_output.json"))
    except Exception as e:
        print(f"WARN: Failed to copy selector_output.json: {e}", file=sys.stderr)

    print(f"Dashboard generated: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
