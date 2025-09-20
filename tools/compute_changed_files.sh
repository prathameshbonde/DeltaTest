#!/usr/bin/env bash
set -euo pipefail

LOG_LEVEL=${LOG_LEVEL:-INFO}
_ts() { date +"%Y-%m-%dT%H:%M:%S"; }
_lvl() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
log() { echo "[$(_ts)] [$(_lvl "$1")] $2"; }
info() { log INFO "$1"; }
warn() { log WARN "$1"; }

# compute_changed_files.sh
# Usage: compute_changed_files.sh <base> <head> <output_json> [project_root]
# Outputs JSON with changed files and hunks.

BASE_REF=${1:-origin/main}
HEAD_REF=${2:-HEAD}
OUT=${3:-tools/output/changed_files.json}
PROJECT_ROOT=${4:-}

# Resolve Python executable (Windows-friendly)
PY=""
if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/Scripts/python.exe" ]]; then
    PY="$VIRTUAL_ENV/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
elif command -v py >/dev/null 2>&1; then
    PY="py -3"
else
    echo "Python interpreter not found. Please install Python 3 or activate your venv." >&2
    mkdir -p "$(dirname "$OUT")"
    echo "[]" > "$OUT"
    exit 0
fi

mkdir -p "$(dirname "$OUT")"

# Build git command to operate within the requested project root
GIT_CMD=(git)
if [[ -n "$PROJECT_ROOT" ]]; then
  if [[ -d "$PROJECT_ROOT" ]]; then
    GIT_CMD=(git -C "$PROJECT_ROOT")
  else
    warn "Project root '$PROJECT_ROOT' does not exist; using current directory."
  fi
fi

# If not a git repo, or no commits yet, write empty changes and exit cleanly
if ! "${GIT_CMD[@]}" rev-parse --git-dir >/dev/null 2>&1; then
    warn "Not a git repository at ${PROJECT_ROOT:-.}; producing empty change set."
    echo "[]" > "$OUT"
    exit 0
fi

exists_commit() {
    "${GIT_CMD[@]}" rev-parse --verify "$1^{commit}" >/dev/null 2>&1
}

# Normalize HEAD ref
if ! exists_commit "$HEAD_REF"; then
    if exists_commit HEAD; then
        warn "Head ref $HEAD_REF not found; using HEAD."
        HEAD_REF="HEAD"
    else
        warn "No commits yet in repo; producing empty change set."
        echo "[]" > "$OUT"
        exit 0
    fi
fi

# Ensure we have a valid base; if missing, use the empty tree so first-commit diffs work
if ! exists_commit "$BASE_REF"; then
    EMPTY_TREE=$("${GIT_CMD[@]}" hash-object -t tree /dev/null 2>/dev/null || echo 4b825dc642cb6eb9a060e54bf8d69288fbee4904)
    warn "Base ref $BASE_REF not found; falling back to empty tree."
    BASE_REF="$EMPTY_TREE"
fi

# Export for Python step
export BASE_REF
export HEAD_REF
export REPO_CWD="$PROJECT_ROOT"

# Collect changed files and hunks using git diff --unified=0
TMP=$(mktemp)
# Windows Git Bash mktemp compatibility
if [[ ! -f "$TMP" ]]; then TMP=$(mktemp -t tmp.XXXXXX); fi

log INFO "Computing git diff between $BASE_REF and $HEAD_REF${PROJECT_ROOT:+ in repo '$PROJECT_ROOT'}"
"${GIT_CMD[@]}" diff --no-color -U0 "$BASE_REF" "$HEAD_REF" > "$TMP" || true

# Run embedded Python, supporting both "python" and "py -3". This enriches each changed file with:
# - file_name: basename of the path
# - lang: simple language guess by extension (e.g., "java")
# - For Java: package, class_name, fully_qualified_class, methods[], and touched_methods[] with line spans
if [[ "$PY" == "py -3" ]]; then
  py -3 - "$TMP" "$OUT" << 'PY'
import json, re, sys, os, subprocess

diff_path, out_path = sys.argv[1], sys.argv[2]
changed = []
current = None
hunk_re = re.compile(r'^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@')
file_re = re.compile(r'^\+\+\+ b\/(.*)$')
change_type_map = {}

base = os.environ.get("BASE_REF","origin/main")
head = os.environ.get("HEAD_REF","HEAD")
repo = os.environ.get("REPO_CWD", "").strip()

args = ["git"]
if repo:
    args += ["-C", repo]
args += ["diff","--name-status", base, head]
try:
    ns = subprocess.check_output(args, text=True)
except Exception:
    ns = ""
for line in ns.strip().splitlines():
    if not line.strip():
        continue
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        typ, path = parts
        change_type_map[path.strip()] = typ

with open(diff_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if line.startswith('+++ b/'):
            path = file_re.match(line).group(1)
            current = {"path": path, "change_type": change_type_map.get(path, "M"), "hunks": []}
            changed.append(current)
        elif line.startswith('@@') and current is not None:
            m = hunk_re.match(line)
            if m:
                start = int(m.group('new_start'))
                count = int(m.group('new_count') or '1')
                current["hunks"].append({"start": start, "end": start + max(count-1,0)})

# --- Enrichment helpers ---
def _detect_lang(path: str):
    _, ext = os.path.splitext(path)
    if ext.lower() == '.java':
        return 'java'
    return ext[1:].lower() if ext.startswith('.') else None

def _git_show(commit, path):
    args = ["git"]
    if repo:
        args += ["-C", repo]
    args += ["show", f"{commit}:{path}"]
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None

def _read_file_for_change(path, change_type):
    if change_type == 'D':
        return _git_show(base, path)
    # default to HEAD for A/M/R
    return _git_show(head, path)

def _parse_java_info(src, path):
    if not src:
        return None
    pkg_m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', src, re.MULTILINE)
    package = pkg_m.group(1) if pkg_m else None
    cls = os.path.basename(path).rsplit('.',1)[0]
    fqc = f"{package}.{cls}" if package else cls

    lines = src.splitlines()
    methods = []
    # Regex targets common method declarations with opening brace on same line
    header_re = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:native\s+)?(?:<[^>]+>\s*)?[\w\[\].<>]+\s+([A-Za-z_][\w$]*)\s*\([^)]*\)\s*(?:throws [^{;]*)?\s*\{')
    for i, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
        name = m.group(1)
        sig = line.strip()
        start_line = i + 1
        # Find end by brace matching starting from this line
        brace = 0
        found_open = False
        end_line = start_line
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == '{':
                    brace += 1
                    found_open = True
                elif ch == '}':
                    brace -= 1
            if found_open and brace == 0:
                end_line = j + 1
                break
        methods.append({
            "name": name,
            "signature": sig,
            "start_line": start_line,
            "end_line": end_line,
            "fqn": f"{fqc}#{name}",
        })

    return {
        "package": package,
        "class_name": cls,
        "fully_qualified_class": fqc,
        "methods": methods,
    }

def _compute_touched_methods(java_info, hunks):
    touched = []
    if not java_info:
        return touched
    for m in java_info.get('methods', []) or []:
        for h in hunks or []:
            if not (h['end'] < m['start_line'] or h['start'] > m['end_line']):
                touched.append(m)
                break
    return touched

# Enrich each changed file record
for cf in changed:
    cf["file_name"] = os.path.basename(cf["path"]) if cf.get("path") else None
    cf["lang"] = _detect_lang(cf["path"]) if cf.get("path") else None
    if cf["lang"] == 'java':
        src = _read_file_for_change(cf["path"], cf.get("change_type","M")) or ""
        jinfo = _parse_java_info(src, cf["path"]) if src else None
        if jinfo:
            cf.update({
                "package": jinfo.get("package"),
                "class_name": jinfo.get("class_name"),
                "fully_qualified_class": jinfo.get("fully_qualified_class"),
            })
            cf["touched_methods"] = _compute_touched_methods(jinfo, cf.get("hunks", []))
        else:
            cf["touched_methods"] = []

with open(out_path,'w',encoding='utf-8') as out:
    json.dump(changed, out, indent=2)
print(f"Wrote {out_path}")
PY
else
  $PY - "$TMP" "$OUT" << 'PY'
import json, re, sys, os, subprocess

diff_path, out_path = sys.argv[1], sys.argv[2]
changed = []
current = None
hunk_re = re.compile(r'^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@')
file_re = re.compile(r'^\+\+\+ b\/(.*)$')
change_type_map = {}

base = os.environ.get("BASE_REF","origin/main")
head = os.environ.get("HEAD_REF","HEAD")
repo = os.environ.get("REPO_CWD", "").strip()

args = ["git"]
if repo:
    args += ["-C", repo]
args += ["diff","--name-status", base, head]
try:
    ns = subprocess.check_output(args, text=True)
except Exception:
    ns = ""
for line in ns.strip().splitlines():
    if not line.strip():
        continue
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        typ, path = parts
        change_type_map[path.strip()] = typ

with open(diff_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if line.startswith('+++ b/'):
            path = file_re.match(line).group(1)
            current = {"path": path, "change_type": change_type_map.get(path, "M"), "hunks": []}
            changed.append(current)
        elif line.startswith('@@') and current is not None:
            m = hunk_re.match(line)
            if m:
                start = int(m.group('new_start'))
                count = int(m.group('new_count') or '1')
                current["hunks"].append({"start": start, "end": start + max(count-1,0)})

# --- Enrichment helpers ---
def _detect_lang(path: str):
    _, ext = os.path.splitext(path)
    if ext.lower() == '.java':
        return 'java'
    return ext[1:].lower() if ext.startswith('.') else None

def _git_show(commit, path):
    args = ["git"]
    if repo:
        args += ["-C", repo]
    args += ["show", f"{commit}:{path}"]
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None

def _read_file_for_change(path, change_type):
    if change_type == 'D':
        return _git_show(base, path)
    return _git_show(head, path)

def _parse_java_info(src, path):
    if not src:
        return None
    pkg_m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', src, re.MULTILINE)
    package = pkg_m.group(1) if pkg_m else None
    cls = os.path.basename(path).rsplit('.',1)[0]
    fqc = f"{package}.{cls}" if package else cls

    lines = src.splitlines()
    methods = []
    header_re = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:native\s+)?(?:<[^>]+>\s*)?[\w\[\].<>]+\s+([A-Za-z_][\w$]*)\s*\([^)]*\)\s*(?:throws [^{;]*)?\s*\{')
    for i, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
        name = m.group(1)
        sig = line.strip()
        start_line = i + 1
        brace = 0
        found_open = False
        end_line = start_line
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == '{':
                    brace += 1
                    found_open = True
                elif ch == '}':
                    brace -= 1
            if found_open and brace == 0:
                end_line = j + 1
                break
        methods.append({
            "name": name,
            "signature": sig,
            "start_line": start_line,
            "end_line": end_line,
            "fqn": f"{fqc}#{name}",
        })

    return {
        "package": package,
        "class_name": cls,
        "fully_qualified_class": fqc,
        "methods": methods,
    }

def _compute_touched_methods(java_info, hunks):
    touched = []
    if not java_info:
        return touched
    for m in java_info.get('methods', []) or []:
        for h in hunks or []:
            if not (h['end'] < m['start_line'] or h['start'] > m['end_line']):
                touched.append(m)
                break
    return touched

for cf in changed:
    cf["file_name"] = os.path.basename(cf["path"]) if cf.get("path") else None
    cf["lang"] = _detect_lang(cf["path"]) if cf.get("path") else None
    if cf["lang"] == 'java':
        src = _read_file_for_change(cf["path"], cf.get("change_type","M")) or ""
        jinfo = _parse_java_info(src, cf["path"]) if src else None
        if jinfo:
            cf.update({
                "package": jinfo.get("package"),
                "class_name": jinfo.get("class_name"),
                "fully_qualified_class": jinfo.get("fully_qualified_class"),
            })
            cf["touched_methods"] = _compute_touched_methods(jinfo, cf.get("hunks", []))
        else:
            cf["touched_methods"] = []

with open(out_path,'w',encoding='utf-8') as out:
    json.dump(changed, out, indent=2)
print(f"Wrote {out_path}")
PY
fi

exit 0
