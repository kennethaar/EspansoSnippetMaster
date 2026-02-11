#!/usr/bin/env python3
"""SnippetMaster - A minimal GUI frontend for Espanso"""
"""
SnippetMaster
───────────────────────────────
A minimal Espanso web-GUI.

Features:
- View, Create, Edit, and Delete snippets.
- Supports standard Text replacements (`replace`) and Markdown (`markdown`).
- Toggles for 'Whole Word' and 'Case Propagation'.
- Auto-detects Espanso configuration directory (Windows/macOS/Linux).
- Filter snippets by source file.
- Sort snippets alphabetically.
- Open folder location for snippet files.
- NEW: Create new snippet files/collections.
- NEW: Move snippets between files.
- NEW: Import external YAML files.
- NEW: Export/copy files for sharing.

Requirements:
1. Espanso installed.
2. Python dependencies: `pip install flask ruamel.yaml`

Usage:
Run "python SnippetMaster.py" and it will open your browser automatically.
"#!/usr/bin/env python3
"""SnippetMaster - A minimal GUI frontend for Espanso"""
"""
SnippetMaster
───────────────────────────────
A minimal Espanso web-GUI.

Features:
- View, Create, Edit, and Delete snippets.
- Supports standard Text replacements (`replace`) and Markdown (`markdown`).
- Toggles for 'Whole Word' and 'Case Propagation'.
- Auto-detects Espanso configuration directory (Windows/macOS/Linux).
- Filter snippets by source file.
- Sort snippets alphabetically.
- Open folder location for snippet files.
- NEW: Create new snippet files/collections.
- NEW: Move snippets between files.
- NEW: Import external YAML files.
- NEW: Export/copy files for sharing.

Requirements:
1. Espanso installed.
2. Python dependencies: `pip install flask ruamel.yaml`

Usage:
Run "python SnippetMaster.py" and it will open your browser automatically.
"""
import os, sys, webbrowser, subprocess, shutil
from pathlib import Path
from threading import Timer
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file
from ruamel.yaml import YAML
from werkzeug.utils import secure_filename

app = Flask(__name__)
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

def get_match_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "espanso" / "match"
    return Path.home() / ".config" / "espanso" / "match"

MATCH_DIR = get_match_dir()

def ensure_absolute_path(path_str):
    if sys.platform != "win32" and not path_str.startswith('/'):
        return '/' + path_str
    return path_str

def get_file_label(filepath):
    """Extract meaningful label - use parent folder name if file is named 'package.yml'"""
    path = Path(filepath)
    if path.stem.lower() == "package":
        return path.parent.name
    return path.stem

def load_snippets():
    snippets = []
    if not MATCH_DIR.exists():
        return snippets, False
    for f in MATCH_DIR.glob("**/*.yml"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.load(fp)
            if data and "matches" in data:
                for i, m in enumerate(data["matches"]):
                    is_markdown = False
                    entry_replace = ""

                    if "markdown" in m:
                        entry_replace = m["markdown"]
                        is_markdown = True
                    else:
                        entry_replace = m.get("replace", "")

                    if not isinstance(entry_replace, str):
                        entry_replace = str(entry_replace)

                    snippets.append({
                        "id": f"{f}::{i}",
                        "file": str(f),
                        "file_label": get_file_label(f),
                        "index": i,
                        "trigger": m.get("trigger", ""),
                        "replace": entry_replace,
                        "word": m.get("word", False),
                        "propagate_case": m.get("propagate_case", False),
                        "is_markdown": is_markdown
                    })
        except Exception as e:
            print(f"Error loading {f}: {e}")
    return snippets, True

def get_yaml_files():
    """Get list of all YAML files in match directory"""
    files = []
    if MATCH_DIR.exists():
        for f in MATCH_DIR.glob("**/*.yml"):
            files.append({
                "path": str(f),
                "label": get_file_label(f),
                "relative": str(f.relative_to(MATCH_DIR))
            })
    return sorted(files, key=lambda x: x["label"].lower())

def save_snippet(filepath, index, trigger, replace, word, pcase, is_markdown, is_new=False):
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            data = loaded if isinstance(loaded, dict) else {}

    if "matches" not in data:
        data["matches"] = []

    entry = {"trigger": trigger}

    if is_markdown:
        entry["markdown"] = replace
    else:
        entry["replace"] = replace

    if word: entry["word"] = True
    if pcase: entry["propagate_case"] = True

    if is_new:
        data["matches"].append(entry)
    else:
        if index < len(data["matches"]):
            orig = data["matches"][index]
            for k in orig:
                if k not in ["trigger", "replace", "markdown", "word", "propagate_case"]:
                    entry[k] = orig[k]
            data["matches"][index] = entry
        else:
            raise IndexError(f"Index {index} out of range.")

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

def delete_snippet(filepath, index):
    filepath = Path(filepath)
    if not filepath.exists(): return
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    if data and "matches" in data and index < len(data["matches"]):
        del data["matches"][index]
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f) if data["matches"] else f.write('')

def move_snippet(source_file, source_index, target_file):
    """Move a snippet from one file to another"""
    source_path = Path(source_file)
    target_path = Path(target_file)
    
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    # Load source file
    with open(source_path, "r", encoding="utf-8") as f:
        source_data = yaml.load(f)
    
    if not source_data or "matches" not in source_data:
        raise ValueError("Source file has no matches")
    
    if source_index >= len(source_data["matches"]):
        raise IndexError(f"Index {source_index} out of range")
    
    # Get the snippet to move
    snippet = source_data["matches"][source_index]
    
    # Load or create target file
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_data = {}
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            target_data = loaded if isinstance(loaded, dict) else {}
    
    if "matches" not in target_data:
        target_data["matches"] = []
    
    # Add to target
    target_data["matches"].append(snippet)
    
    # Remove from source
    del source_data["matches"][source_index]
    
    # Save both files
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump(target_data, f)
    
    with open(source_path, "w", encoding="utf-8") as f:
        if source_data["matches"]:
            yaml.dump(source_data, f)
        else:
            f.write('')

def copy_snippets_to_file(snippet_ids, target_file):
    """Copy multiple snippets to a target file (for export)"""
    target_path = Path(target_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    target_data = {"matches": []}
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            if loaded and "matches" in loaded:
                target_data = loaded
    
    snippets, _ = load_snippets()
    snippets_by_id = {s["id"]: s for s in snippets}
    
    for sid in snippet_ids:
        if sid in snippets_by_id:
            s = snippets_by_id[sid]
            # Load original entry from file to preserve all fields
            source_path = Path(s["file"])
            with open(source_path, "r", encoding="utf-8") as f:
                source_data = yaml.load(f)
            if source_data and "matches" in source_data and s["index"] < len(source_data["matches"]):
                entry = source_data["matches"][s["index"]]
                target_data["matches"].append(entry)
    
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump(target_data, f)
    
    return len(snippet_ids)

def import_yaml_file(source_path, merge_into=None):
    """Import a YAML file into Espanso match directory"""
    source_path = Path(source_path)
    
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")
    
    # Validate it's a valid Espanso file
    with open(source_path, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    
    if not data or "matches" not in data:
        raise ValueError("Invalid Espanso file: no 'matches' key found")
    
    if merge_into:
        # Merge into existing file
        target_path = Path(merge_into)
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                target_data = yaml.load(f)
            if target_data and "matches" in target_data:
                target_data["matches"].extend(data["matches"])
            else:
                target_data = data
        else:
            target_data = data
        
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(target_data, f)
        
        return len(data["matches"]), target_path
    else:
        # Copy as new file
        target_name = source_path.stem
        target_path = MATCH_DIR / f"{target_name}.yml"
        
        # Avoid overwriting
        counter = 1
        while target_path.exists():
            target_path = MATCH_DIR / f"{target_name}_{counter}.yml"
            counter += 1
        
        shutil.copy(source_path, target_path)
        return len(data["matches"]), target_path

def create_new_file(filename):
    """Create a new empty YAML file"""
    if not filename.endswith('.yml'):
        filename += '.yml'
    
    # Sanitize filename
    filename = secure_filename(filename)
    filepath = MATCH_DIR / filename
    
    if filepath.exists():
        raise FileExistsError(f"File already exists: {filename}")
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Create empty matches file
    data = {"matches": []}
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    
    return filepath

def open_folder(folder_path):
    """Open the folder in the system file manager"""
    folder_path = Path(folder_path)
    if not folder_path.exists():
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(['explorer', str(folder_path)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(['open', str(folder_path)], check=False)
        else:
            subprocess.run(['xdg-open', str(folder_path)], check=False)
        return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False

TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SnippetMaster</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root {
    --bg-primary: #0d0d14;
    --bg-secondary: #16161f;
    --bg-card: #1e1e2a;
    --bg-card-hover: #262636;
    --text-primary: #e8e8ed;
    --text-secondary: #8b8b9e;
    --text-muted: #5a5a6e;
    --accent-blue: #3b82f6;
    --accent-blue-hover: #2563eb;
    --accent-green: #22c55e;
    --accent-green-hover: #16a34a;
    --accent-red: #ef4444;
    --accent-red-hover: #dc2626;
    --accent-purple: #a855f7;
    --accent-purple-hover: #9333ea;
    --border-color: #2a2a3a;
    --badge-bg: #2a2a3a;
    --badge-text: #a0a0b8;
    --badge-yellow-bg: #422006;
    --badge-yellow-text: #fbbf24;
    --badge-blue-bg: #172554;
    --badge-blue-text: #60a5fa;
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    --radius: 8px;
    --radius-lg: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.5;
}

.container { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 24px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-color);
}

.header-left { display: flex; align-items: baseline; gap: 12px; }

.logo {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

.logo:hover { color: var(--accent-blue); }

.snippet-count { font-size: 0.95rem; color: var(--text-secondary); font-weight: 400; }

.header-right { display: flex; align-items: center; gap: 12px; }

.search-container { position: relative; }

.search-icon {
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
}

.search-input {
    width: 240px;
    padding: 10px 16px 10px 42px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    transition: all 0.2s ease;
}

.search-input::placeholder { color: var(--text-muted); }
.search-input:focus { outline: none; border-color: var(--accent-blue); background: var(--bg-card); }

.btn {
    padding: 10px 18px;
    border-radius: var(--radius);
    border: none;
    font-size: 0.9rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
}

.btn-primary { background: var(--accent-blue); color: white; }
.btn-primary:hover { background: var(--accent-blue-hover); transform: translateY(-1px); }

.btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-secondary:hover { background: var(--bg-card-hover); border-color: var(--text-muted); }

.btn-success { background: var(--accent-green); color: white; }
.btn-success:hover { background: var(--accent-green-hover); }

.btn-purple { background: var(--accent-purple); color: white; }
.btn-purple:hover { background: var(--accent-purple-hover); }

.btn-danger { background: var(--accent-red); color: white; }
.btn-danger:hover { background: var(--accent-red-hover); }

.btn-icon { width: 38px; height: 38px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); }

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.controls-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}

.control-select {
    padding: 10px 36px 10px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238b8b9e' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    transition: all 0.2s ease;
}

.control-select:hover { border-color: var(--text-muted); }
.control-select:focus { outline: none; border-color: var(--accent-blue); }

.btn-folder { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); display: none; }
.btn-folder:hover { background: var(--bg-card-hover); border-color: var(--text-muted); }

.filtered-count { font-size: 0.9rem; color: var(--text-secondary); margin-left: auto; }

/* Selection Mode */
.selection-bar {
    display: none;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--accent-purple);
    border-radius: var(--radius);
    margin-bottom: 16px;
}

.selection-bar.active { display: flex; }

.selection-count { font-weight: 500; color: var(--accent-purple); }

.snippet-checkbox {
    width: 20px;
    height: 20px;
    accent-color: var(--accent-purple);
    cursor: pointer;
    margin-right: 12px;
    display: none;
}

.selection-mode .snippet-checkbox { display: block; }
.selection-mode .snippet-card { cursor: default; }
.selection-mode .snippet-card:hover { transform: none; }

#snippet-list { display: flex; flex-direction: column; gap: 10px; }

.snippet-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 16px 20px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.2s ease;
    position: relative;
}

.snippet-card:hover { background: var(--bg-card-hover); border-color: var(--text-muted); transform: translateX(2px); }
.snippet-card.selected { border-color: var(--accent-purple); background: rgba(168, 85, 247, 0.1); }

.snippet-content { flex: 1; min-width: 0; display: flex; align-items: center; }
.snippet-info { flex: 1; min-width: 0; }

.snippet-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }

.snippet-trigger { font-family: 'JetBrains Mono', monospace; font-weight: 500; font-size: 1rem; color: var(--accent-blue); }

.badge { padding: 3px 8px; font-size: 0.75rem; font-weight: 500; border-radius: 4px; background: var(--badge-bg); color: var(--badge-text); }
.badge-file { background: var(--badge-bg); color: var(--badge-text); }
.badge-word { background: var(--badge-bg); color: var(--badge-text); }
.badge-case { background: var(--badge-bg); color: var(--badge-text); }
.badge-md { background: var(--badge-blue-bg); color: var(--badge-blue-text); }

.snippet-preview { font-size: 0.9rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 600px; }

.snippet-actions { display: flex; gap: 8px; opacity: 0; transition: opacity 0.2s ease; }
.snippet-card:hover .snippet-actions { opacity: 1; }

.btn-edit { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-edit:hover { background: var(--accent-blue); border-color: var(--accent-blue); }

.btn-delete { background: var(--accent-red); color: white; }
.btn-delete:hover { background: var(--accent-red-hover); }

.message {
    padding: 14px 18px;
    border-radius: var(--radius);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 500;
}

.message-success { background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); color: var(--accent-green); }
.message-error { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--accent-red); }

.empty-state { text-align: center; padding: 80px 20px; color: var(--text-secondary); }
.empty-state h2 { font-size: 1.5rem; color: var(--text-primary); margin-bottom: 12px; }
.empty-state p { font-size: 1rem; }

.back-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.9rem;
    margin-bottom: 24px;
    transition: color 0.2s ease;
}

.back-link:hover { color: var(--accent-blue); }

.form-title { font-size: 1.75rem; font-weight: 600; margin-bottom: 32px; color: var(--text-primary); }

.form-group { margin-bottom: 24px; }

.form-label { display: block; font-size: 0.9rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 8px; }

.form-input, .form-textarea {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.95rem;
    font-family: inherit;
    transition: all 0.2s ease;
}

.form-textarea { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; resize: vertical; min-height: 200px; }

.form-input:focus, .form-textarea:focus { outline: none; border-color: var(--accent-blue); background: var(--bg-card); }
.form-input::placeholder, .form-textarea::placeholder { color: var(--text-muted); }

.options-box { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px 20px; }

.option-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
.option-item:not(:last-child) { border-bottom: 1px solid var(--border-color); }
.option-item input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--accent-blue); cursor: pointer; }
.option-item label { font-size: 0.9rem; color: var(--text-primary); cursor: pointer; }

.form-actions { margin-top: 32px; display: flex; gap: 12px; }

/* Modal */
.modal-overlay {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    z-index: 1000;
    align-items: center;
    justify-content: center;
}

.modal-overlay.active { display: flex; }

.modal {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
}

.modal-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 20px; }

.modal-actions { display: flex; gap: 12px; margin-top: 24px; justify-content: flex-end; }

/* File list in modal */
.file-list { max-height: 300px; overflow-y: auto; margin: 16px 0; }

.file-item {
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    margin-bottom: 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 10px;
}

.file-item:hover { border-color: var(--accent-blue); background: var(--bg-card-hover); }
.file-item.selected { border-color: var(--accent-purple); background: rgba(168, 85, 247, 0.15); }

.file-item-label { font-weight: 500; }
.file-item-path { font-size: 0.8rem; color: var(--text-muted); }

/* File input styling */
.file-input-wrapper { position: relative; }

.file-input-wrapper input[type="file"] {
    position: absolute;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
}

.file-input-label {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 40px 20px;
    background: var(--bg-secondary);
    border: 2px dashed var(--border-color);
    border-radius: var(--radius);
    color: var(--text-secondary);
    transition: all 0.2s ease;
}

.file-input-wrapper:hover .file-input-label { border-color: var(--accent-blue); color: var(--accent-blue); }

.selected-file { margin-top: 12px; padding: 10px 14px; background: var(--bg-secondary); border-radius: var(--radius); font-size: 0.9rem; }

/* Dropdown menu */
.dropdown { position: relative; }

.dropdown-menu {
    display: none;
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    min-width: 180px;
    z-index: 100;
    box-shadow: var(--shadow);
}

.dropdown-menu.active { display: block; }

.dropdown-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    color: var(--text-primary);
    text-decoration: none;
    transition: background 0.2s ease;
    cursor: pointer;
    border: none;
    background: none;
    width: 100%;
    font-size: 0.9rem;
    font-family: inherit;
}

.dropdown-item:hover { background: var(--bg-card-hover); }
.dropdown-item:first-child { border-radius: var(--radius) var(--radius) 0 0; }
.dropdown-item:last-child { border-radius: 0 0 var(--radius) var(--radius); }

.dropdown-divider { height: 1px; background: var(--border-color); margin: 4px 0; }

@media (max-width: 768px) {
    .container { padding: 16px; }
    header { flex-direction: column; gap: 16px; align-items: flex-start; }
    .header-right { width: 100%; flex-direction: column; align-items: stretch; }
    .search-input { width: 100%; }
    .controls-bar { flex-direction: column; align-items: stretch; }
    .control-select { width: 100%; }
    .filtered-count { margin-left: 0; text-align: center; }
    .snippet-actions { opacity: 1; }
    .snippet-preview { max-width: 100%; }
}
</style>
</head>
<body>
<div class="container">
<header>
<div class="header-left">
    <a href="/" class="logo">
        <span>⌨</span>
        <span>SnippetMaster</span>
    </a>
    {% if snippet_count is defined %}<span class="snippet-count">({{ snippet_count }} snippet{{ 's' if snippet_count != 1 else '' }})</span>{% endif %}
</div>
{% if view != 'error' %}
<div class="header-right">
    <div class="search-container">
        <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
        </svg>
        <input type="text" id="search-input" class="search-input" placeholder="Search">
    </div>
    <a href="/new" class="btn btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5v14M5 12h14"/>
        </svg>
        Add New
    </a>
    <div class="dropdown">
        <button class="btn btn-secondary" id="menu-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="1"></circle>
                <circle cx="12" cy="5" r="1"></circle>
                <circle cx="12" cy="19" r="1"></circle>
            </svg>
            More
        </button>
        <div class="dropdown-menu" id="menu-dropdown">
            <button class="dropdown-item" onclick="openModal('new-file-modal')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="12" y1="18" x2="12" y2="12"></line>
                    <line x1="9" y1="15" x2="15" y2="15"></line>
                </svg>
                New Collection
            </button>
            <button class="dropdown-item" onclick="openModal('import-modal')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Import Collection
            </button>
            <div class="dropdown-divider"></div>
            <button class="dropdown-item" id="toggle-selection-btn" onclick="toggleSelectionMode()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 11 12 14 22 4"></polyline>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                </svg>
                Select Snippets
            </button>
            <div class="dropdown-divider"></div>
            <button class="dropdown-item" onclick="openMatchDir()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
                Open Espanso Folder
            </button>
        </div>
    </div>
</div>
{% endif %}
</header>

<main>
{% if msg %}
<div class="message {{ 'message-success' if mt == 'success' else 'message-error' }}">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        {% if mt == 'success' %}
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
        {% else %}
        <circle cx="12" cy="12" r="10"></circle>
        <path d="m15 9-6 6M9 9l6 6"/>
        {% endif %}
    </svg>
    <span>{{ msg }}</span>
</div>
{% endif %}

{% if view == 'list' %}
    <!-- Selection Bar -->
    <div class="selection-bar" id="selection-bar">
        <span class="selection-count"><span id="selected-count">0</span> selected</span>
        <button class="btn btn-sm btn-purple" onclick="openMoveModal()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            Move to...
        </button>
        <button class="btn btn-sm btn-success" onclick="openExportModal()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            Export...
        </button>
        <button class="btn btn-sm btn-secondary" onclick="toggleSelectionMode()">Cancel</button>
    </div>

    {% if snippets %}
    <div class="controls-bar">
        <select id="filter-file" class="control-select">
            <option value="all">Collection: All files</option>
            {% for file in unique_files %}
            <option value="{{ file.path }}">Collection: {{ file.label }}</option>
            {% endfor %}
        </select>
        <select id="sort-order" class="control-select">
            <option value="asc">Sort: A → Z</option>
            <option value="desc">Sort: Z → A</option>
        </select>
        <button id="btn-open-folder" class="btn btn-folder" title="Open folder in file manager">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
            Open Folder
        </button>
        <span id="filtered-count" class="filtered-count"></span>
    </div>

    <div id="snippet-list">
        {% for s in snippets %}
        <div class="snippet-card" data-file="{{ s.file }}" data-trigger="{{ s.trigger|lower }}" data-id="{{ s.id|urlencode }}">
            <div class="snippet-content">
                <input type="checkbox" class="snippet-checkbox" data-id="{{ s.id|urlencode }}" onclick="event.stopPropagation(); updateSelectionCount();">
                <div class="snippet-info">
                    <div class="snippet-header">
                        <span class="snippet-trigger">{{ s.trigger }}</span>
                        <span class="badge badge-file">{{ s.file_label }}</span>
                        {% if s.word %}<span class="badge badge-word">word</span>{% endif %}
                        {% if s.propagate_case %}<span class="badge badge-case">case</span>{% endif %}
                        {% if s.is_markdown %}<span class="badge badge-md">md</span>{% endif %}
                    </div>
                    <div class="snippet-preview">Expansion: {{ s.replace.split('\n')[0][:80] }}</div>
                </div>
            </div>
            <div class="snippet-actions">
                <a href="/edit/{{ s.id|urlencode }}" class="btn btn-icon btn-edit" onclick="event.stopPropagation();" title="Edit">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                </a>
                <a href="/delete/{{ s.id|urlencode }}" class="btn btn-icon btn-delete" onclick="event.stopPropagation();" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </a>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
        <div class="empty-state">
            <h2>No snippets yet</h2>
            <p>Click <strong>+ Add New</strong> to create your first snippet, or import an existing collection.</p>
        </div>
    {% endif %}

<!-- New File Modal -->
<div class="modal-overlay" id="new-file-modal">
    <div class="modal">
        <h2 class="modal-title">Create New Collection</h2>
        <form id="new-file-form" action="/create-file" method="POST">
            <div class="form-group">
                <label class="form-label" for="new-filename">Collection Name</label>
                <input type="text" id="new-filename" name="filename" class="form-input" placeholder="my-snippets" required>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">.yml extension will be added automatically</p>
            </div>
            <div class="modal-actions">
                <button type="button" class="btn btn-secondary" onclick="closeModal('new-file-modal')">Cancel</button>
                <button type="submit" class="btn btn-primary">Create</button>
            </div>
        </form>
    </div>
</div>

<!-- Import Modal -->
<div class="modal-overlay" id="import-modal">
    <div class="modal">
        <h2 class="modal-title">Import Collection</h2>
        <form id="import-form" action="/import" method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label class="form-label">Select YAML file</label>
                <div class="file-input-wrapper">
                    <input type="file" id="import-file" name="file" accept=".yml,.yaml" required onchange="updateFileLabel(this)">
                    <div class="file-input-label">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        <span>Click to select or drag and drop</span>
                    </div>
                </div>
                <div id="selected-file-name" class="selected-file" style="display: none;"></div>
            </div>
            <div class="form-group">
                <label class="form-label">Import as</label>
                <div class="option-item" style="padding: 0;">
                    <input type="radio" id="import-new" name="import_mode" value="new" checked>
                    <label for="import-new">New collection (keep original filename)</label>
                </div>
                <div class="option-item" style="border: none;">
                    <input type="radio" id="import-merge" name="import_mode" value="merge">
                    <label for="import-merge">Merge into existing collection</label>
                </div>
                <select id="merge-target" name="merge_target" class="control-select" style="width: 100%; margin-top: 8px; display: none;">
                    {% for file in unique_files %}
                    <option value="{{ file.path }}">{{ file.label }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="modal-actions">
                <button type="button" class="btn btn-secondary" onclick="closeModal('import-modal')">Cancel</button>
                <button type="submit" class="btn btn-success">Import</button>
            </div>
        </form>
    </div>
</div>

<!-- Move Modal -->
<div class="modal-overlay" id="move-modal">
    <div class="modal">
        <h2 class="modal-title">Move Snippets</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">Select destination collection:</p>
        <div class="file-list" id="move-file-list">
            {% for file in unique_files %}
            <div class="file-item" data-path="{{ file.path }}" onclick="selectMoveTarget(this)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <div>
                    <div class="file-item-label">{{ file.label }}</div>
                    <div class="file-item-path">{{ file.relative }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        <div style="margin-top: 12px;">
            <button class="btn btn-sm btn-secondary" onclick="showNewFileInMove()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 5v14M5 12h14"/>
                </svg>
                Create new collection
            </button>
        </div>
        <div id="move-new-file" style="display: none; margin-top: 12px;">
            <input type="text" id="move-new-filename" class="form-input" placeholder="new-collection-name">
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" onclick="closeModal('move-modal')">Cancel</button>
            <button type="button" class="btn btn-purple" id="move-confirm-btn" onclick="confirmMove()">Move</button>
        </div>
    </div>
</div>

<!-- Export Modal -->
<div class="modal-overlay" id="export-modal">
    <div class="modal">
        <h2 class="modal-title">Export Snippets</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">Export selected snippets to a new file for sharing.</p>
        <div class="form-group">
            <label class="form-label" for="export-filename">Export filename</label>
            <input type="text" id="export-filename" class="form-input" placeholder="shared-snippets" value="shared-snippets">
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">.yml extension will be added automatically</p>
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" onclick="closeModal('export-modal')">Cancel</button>
            <button type="button" class="btn btn-success" onclick="confirmExport()">Export & Download</button>
        </div>
    </div>
</div>

<script>
(function() {
    const filterSelect = document.getElementById('filter-file');
    const sortSelect = document.getElementById('sort-order');
    const openFolderBtn = document.getElementById('btn-open-folder');
    const filteredCountSpan = document.getElementById('filtered-count');
    const snippetList = document.getElementById('snippet-list');
    const searchInput = document.getElementById('search-input');
    const cards = snippetList ? Array.from(snippetList.querySelectorAll('.snippet-card')) : [];
    const menuBtn = document.getElementById('menu-btn');
    const menuDropdown = document.getElementById('menu-dropdown');

    let searchQuery = '';
    let selectionMode = false;

    // Dropdown menu
    if (menuBtn) {
        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            menuDropdown.classList.toggle('active');
        });
        document.addEventListener('click', () => menuDropdown.classList.remove('active'));
    }

    // Click handler for cards
    cards.forEach(card => {
        card.addEventListener('click', function(e) {
            if (selectionMode) {
                const checkbox = this.querySelector('.snippet-checkbox');
                checkbox.checked = !checkbox.checked;
                this.classList.toggle('selected', checkbox.checked);
                updateSelectionCount();
            } else if (!e.target.closest('.snippet-actions')) {
                location.href = '/edit/' + this.dataset.id;
            }
        });
    });

    function applyFilterAndSort() {
        if (!filterSelect || !sortSelect) return;
        
        const filterValue = filterSelect.value;
        const sortValue = sortSelect.value;

        if (openFolderBtn) {
            if (filterValue === 'all') {
                openFolderBtn.style.display = 'none';
            } else {
                openFolderBtn.style.display = 'inline-flex';
                openFolderBtn.dataset.filepath = filterValue;
            }
        }

        let visibleCards = cards.filter(card => {
            const matchesFile = filterValue === 'all' || card.dataset.file === filterValue;
            const matchesSearch = !searchQuery ||
                card.dataset.trigger.includes(searchQuery.toLowerCase()) ||
                card.querySelector('.snippet-preview').textContent.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesFile && matchesSearch;
        });

        visibleCards.sort((a, b) => {
            const triggerA = a.dataset.trigger;
            const triggerB = b.dataset.trigger;
            return sortValue === 'asc' ? triggerA.localeCompare(triggerB) : triggerB.localeCompare(triggerA);
        });

        cards.forEach(card => card.style.display = 'none');
        visibleCards.forEach(card => {
            card.style.display = 'flex';
            snippetList.appendChild(card);
        });

        const total = cards.length;
        const visible = visibleCards.length;
        if (filteredCountSpan) {
            filteredCountSpan.textContent = (filterValue === 'all' && !searchQuery) ? '' : `Showing ${visible} of ${total}`;
        }
    }

    if (filterSelect) filterSelect.addEventListener('change', applyFilterAndSort);
    if (sortSelect) sortSelect.addEventListener('change', applyFilterAndSort);
    if (searchInput) searchInput.addEventListener('input', function() { searchQuery = this.value; applyFilterAndSort(); });

    if (openFolderBtn) {
        openFolderBtn.addEventListener('click', function() {
            const filepath = this.dataset.filepath;
            if (filepath) {
                fetch('/open-folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filepath: filepath })
                }).then(r => r.json()).then(data => {
                    if (!data.success) alert('Could not open folder: ' + (data.error || 'Unknown error'));
                }).catch(() => alert('Error opening folder'));
            }
        });
    }

    applyFilterAndSort();

    // Selection mode
    window.toggleSelectionMode = function() {
        selectionMode = !selectionMode;
        document.body.classList.toggle('selection-mode', selectionMode);
        document.getElementById('selection-bar').classList.toggle('active', selectionMode);
        document.getElementById('toggle-selection-btn').innerHTML = selectionMode ? 
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg> Cancel Selection' :
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg> Select Snippets';
        
        if (!selectionMode) {
            document.querySelectorAll('.snippet-checkbox').forEach(cb => cb.checked = false);
            document.querySelectorAll('.snippet-card').forEach(card => card.classList.remove('selected'));
            updateSelectionCount();
        }
        menuDropdown.classList.remove('active');
    };

    window.updateSelectionCount = function() {
        const count = document.querySelectorAll('.snippet-checkbox:checked').length;
        document.getElementById('selected-count').textContent = count;
    };

    // Modals
    window.openModal = function(id) {
        document.getElementById(id).classList.add('active');
        menuDropdown.classList.remove('active');
    };

    window.closeModal = function(id) {
        document.getElementById(id).classList.remove('active');
    };

    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', function(e) {
            if (e.target === this) this.classList.remove('active');
        });
    });

    // Import modal - toggle merge target
    document.querySelectorAll('input[name="import_mode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.getElementById('merge-target').style.display = this.value === 'merge' ? 'block' : 'none';
        });
    });

    window.updateFileLabel = function(input) {
        const fileName = input.files[0]?.name;
        const display = document.getElementById('selected-file-name');
        if (fileName) {
            display.textContent = 'Selected: ' + fileName;
            display.style.display = 'block';
        } else {
            display.style.display = 'none';
        }
    };

    // Move modal
    let selectedMoveTarget = null;
    let createNewInMove = false;

    window.openMoveModal = function() {
        selectedMoveTarget = null;
        createNewInMove = false;
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        document.getElementById('move-new-file').style.display = 'none';
        document.getElementById('move-new-filename').value = '';
        openModal('move-modal');
    };

    window.selectMoveTarget = function(el) {
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        el.classList.add('selected');
        selectedMoveTarget = el.dataset.path;
        createNewInMove = false;
        document.getElementById('move-new-file').style.display = 'none';
    };

    window.showNewFileInMove = function() {
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        selectedMoveTarget = null;
        createNewInMove = true;
        document.getElementById('move-new-file').style.display = 'block';
        document.getElementById('move-new-filename').focus();
    };

    window.confirmMove = function() {
        const selected = Array.from(document.querySelectorAll('.snippet-checkbox:checked')).map(cb => cb.dataset.id);
        if (selected.length === 0) { alert('No snippets selected'); return; }

        let targetFile = selectedMoveTarget;
        if (createNewInMove) {
            const newName = document.getElementById('move-new-filename').value.trim();
            if (!newName) { alert('Please enter a collection name'); return; }
            targetFile = '_new_:' + newName;
        }

        if (!targetFile) { alert('Please select a destination'); return; }

        fetch('/move-snippets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ snippets: selected, target: targetFile })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                location.href = '/?msg=' + encodeURIComponent(data.message) + '&mt=success';
            } else {
                alert('Error: ' + data.error);
            }
        }).catch(err => alert('Error moving snippets'));
    };

    // Export modal
    window.openExportModal = function() {
        const count = document.querySelectorAll('.snippet-checkbox:checked').length;
        if (count === 0) { alert('No snippets selected'); return; }
        document.getElementById('export-filename').value = 'shared-snippets';
        openModal('export-modal');
    };

    window.confirmExport = function() {
        const selected = Array.from(document.querySelectorAll('.snippet-checkbox:checked')).map(cb => cb.dataset.id);
        const filename = document.getElementById('export-filename').value.trim() || 'shared-snippets';

        fetch('/export-snippets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ snippets: selected, filename: filename })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                // Trigger download
                window.location.href = '/download-export/' + encodeURIComponent(data.filename);
                closeModal('export-modal');
                toggleSelectionMode();
            } else {
                alert('Error: ' + data.error);
            }
        }).catch(err => alert('Error exporting snippets'));
    };

    window.openMatchDir = function() {
        fetch('/open-match-dir', { method: 'POST' })
            .then(r => r.json())
            .then(data => { if (!data.success) alert('Could not open folder'); })
            .catch(() => alert('Error opening folder'));
        menuDropdown.classList.remove('active');
    };
})();
</script>

{% elif view == 'edit' or view == 'new' %}
    <a href="/" class="back-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m15 18-6-6 6-6"/>
        </svg>
        Back to list
    </a>
    <h1 class="form-title">{{ 'Edit Snippet' if view == 'edit' else 'Add New Snippet' }}</h1>
    <form method="POST" action="{{ '/update/' + (snippet.id|urlencode) if view == 'edit' else '/create' }}">
        {% if view == 'new' %}
        <div class="form-group">
            <label class="form-label" for="target_file">Save to Collection</label>
            <select id="target_file" name="target_file" class="control-select" style="width: 100%;">
                <option value="">Default (base.yml)</option>
                {% for file in unique_files %}
                <option value="{{ file.path }}">{{ file.label }}</option>
                {% endfor %}
            </select>
        </div>
        {% endif %}
        <div class="form-group">
            <label class="form-label" for="trigger">Trigger</label>
            <input type="text" id="trigger" name="trigger" class="form-input" value="{{ snippet.trigger if snippet else '' }}" placeholder=":trigger">
        </div>
        <div class="form-group">
            <label class="form-label" for="replace">Replacement</label>
            <textarea id="replace" name="replace" class="form-textarea" rows="10">{{ snippet.replace if snippet else '' }}</textarea>
        </div>
        <div class="form-group">
            <label class="form-label">Options</label>
            <div class="options-box">
                <div class="option-item">
                    <input type="checkbox" id="word" name="word" {{ 'checked' if snippet and snippet.word else '' }}>
                    <label for="word">Expand only if a whole word</label>
                </div>
                <div class="option-item">
                    <input type="checkbox" id="propagate_case" name="propagate_case" {{ 'checked' if snippet and snippet.propagate_case else '' }}>
                    <label for="propagate_case">Propagate case</label>
                </div>
                <div class="option-item">
                    <input type="checkbox" id="markdown" name="markdown" {{ 'checked' if snippet and snippet.is_markdown else '' }}>
                    <label for="markdown">Paste as Markdown</label>
                </div>
            </div>
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
                    <polyline points="17 21 17 13 7 13 7 21"></polyline>
                    <polyline points="7 3 7 8 15 8"></polyline>
                </svg>
                {{ 'Save Changes' if view == 'edit' else 'Create Snippet' }}
            </button>
            <a href="/" class="btn btn-secondary">Cancel</a>
        </div>
    </form>
{% endif %}
</main>
</div>
</body>
</html>'''

@app.route("/")
def index():
    snippets, exists = load_snippets()
    if not exists: return "Espanso match dir not found"

    unique_files_dict = {}
    for s in snippets:
        if s["file"] not in unique_files_dict:
            unique_files_dict[s["file"]] = s["file_label"]

    unique_files = [{"path": path, "label": label, "relative": str(Path(path).relative_to(MATCH_DIR)) if Path(path).is_relative_to(MATCH_DIR) else path} 
                    for path, label in sorted(unique_files_dict.items(), key=lambda x: x[1].lower())]

    return render_template_string(TEMPLATE, view="list", snippets=snippets,
                                  snippet_count=len(snippets),
                                  unique_files=unique_files,
                                  msg=request.args.get("msg"), mt=request.args.get("mt"))

@app.route("/new")
def new_snippet():
    unique_files = get_yaml_files()
    return render_template_string(TEMPLATE, view="new", snippet=None, unique_files=unique_files)

@app.route("/edit/<path:snippet_id>")
def edit_snippet(snippet_id):
    snippets, _ = load_snippets()
    full_id = ensure_absolute_path(snippet_id)
    snippet = next((s for s in snippets if s["id"] == full_id), None)
    if not snippet: snippet = next((s for s in snippets if s["id"] == snippet_id), None)
    return render_template_string(TEMPLATE, view="edit", snippet=snippet, unique_files=[])

@app.route("/create", methods=["POST"])
def create():
    try:
        target_file = request.form.get("target_file", "").strip()
        if not target_file:
            target_file = MATCH_DIR / "base.yml"
        else:
            target_file = Path(target_file)
        
        save_snippet(target_file, 0, request.form.get("trigger").strip(),
                     request.form.get("replace"), "word" in request.form,
                     "propagate_case" in request.form, "markdown" in request.form, is_new=True)
        return redirect(url_for("index", msg="Created", mt="success"))
    except Exception as e: return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/update/<path:snippet_id>", methods=["POST"])
def update(snippet_id):
    try:
        filepath, index = ensure_absolute_path(snippet_id).rsplit("::", 1)
        save_snippet(filepath, int(index), request.form.get("trigger").strip(),
                     request.form.get("replace"), "word" in request.form,
                     "propagate_case" in request.form, "markdown" in request.form)
        return redirect(url_for("index", msg="Saved", mt="success"))
    except Exception as e: return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/delete/<path:snippet_id>")
def delete(snippet_id):
    filepath, index = ensure_absolute_path(snippet_id).rsplit("::", 1)
    delete_snippet(filepath, int(index))
    return redirect(url_for("index", msg="Deleted", mt="success"))

@app.route("/open-folder", methods=["POST"])
def open_folder_route():
    try:
        data = request.get_json()
        filepath = data.get("filepath", "")
        if not filepath:
            return jsonify({"success": False, "error": "No filepath provided"})
        folder_path = Path(filepath).parent
        success = open_folder(folder_path)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/open-match-dir", methods=["POST"])
def open_match_dir_route():
    success = open_folder(MATCH_DIR)
    return jsonify({"success": success})

@app.route("/create-file", methods=["POST"])
def create_file_route():
    try:
        filename = request.form.get("filename", "").strip()
        if not filename:
            return redirect(url_for("index", msg="Filename required", mt="error"))
        
        filepath = create_new_file(filename)
        return redirect(url_for("index", msg=f"Created collection: {filepath.stem}", mt="success"))
    except FileExistsError as e:
        return redirect(url_for("index", msg=str(e), mt="error"))
    except Exception as e:
        return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/import", methods=["POST"])
def import_route():
    try:
        if 'file' not in request.files:
            return redirect(url_for("index", msg="No file selected", mt="error"))
        
        file = request.files['file']
        if file.filename == '':
            return redirect(url_for("index", msg="No file selected", mt="error"))
        
        # Save uploaded file temporarily
        temp_path = Path("/tmp") / secure_filename(file.filename)
        file.save(temp_path)
        
        import_mode = request.form.get("import_mode", "new")
        merge_target = request.form.get("merge_target") if import_mode == "merge" else None
        
        count, target_path = import_yaml_file(temp_path, merge_target)
        
        # Clean up temp file
        temp_path.unlink()
        
        action = "merged into" if merge_target else "imported as"
        return redirect(url_for("index", msg=f"Imported {count} snippets {action} {target_path.stem}", mt="success"))
    except Exception as e:
        return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/move-snippets", methods=["POST"])
def move_snippets_route():
    try:
        data = request.get_json()
        snippet_ids = data.get("snippets", [])
        target = data.get("target", "")
        
        if not snippet_ids:
            return jsonify({"success": False, "error": "No snippets selected"})
        
        if not target:
            return jsonify({"success": False, "error": "No target selected"})
        
        # Check if creating new file
        if target.startswith("_new_:"):
            new_name = target[6:]
            target_path = create_new_file(new_name)
        else:
            target_path = Path(target)
        
        # Decode snippet IDs and move them (in reverse order to handle index shifting)
        from urllib.parse import unquote
        decoded_ids = [unquote(sid) for sid in snippet_ids]
        
        # Group by file and sort by index descending
        by_file = {}
        for sid in decoded_ids:
            sid = ensure_absolute_path(sid)
            filepath, index = sid.rsplit("::", 1)
            if filepath not in by_file:
                by_file[filepath] = []
            by_file[filepath].append(int(index))
        
        # Sort indices in descending order to avoid index shifting issues
        moved_count = 0
        for filepath, indices in by_file.items():
            for index in sorted(indices, reverse=True):
                if Path(filepath) != target_path:  # Don't move to same file
                    move_snippet(filepath, index, target_path)
                    moved_count += 1
        
        return jsonify({"success": True, "message": f"Moved {moved_count} snippet(s) to {target_path.stem}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/export-snippets", methods=["POST"])
def export_snippets_route():
    try:
        data = request.get_json()
        snippet_ids = data.get("snippets", [])
        filename = data.get("filename", "export")
        
        if not snippet_ids:
            return jsonify({"success": False, "error": "No snippets selected"})
        
        # Decode snippet IDs
        from urllib.parse import unquote
        decoded_ids = [ensure_absolute_path(unquote(sid)) for sid in snippet_ids]
        
        # Create export file in temp directory
        if not filename.endswith('.yml'):
            filename += '.yml'
        export_path = Path("/tmp") / secure_filename(filename)
        
        count = copy_snippets_to_file(decoded_ids, export_path)
        
        return jsonify({"success": True, "filename": export_path.name, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/download-export/<filename>")
def download_export(filename):
    export_path = Path("/tmp") / secure_filename(filename)
    if not export_path.exists():
        return redirect(url_for("index", msg="Export file not found", mt="error"))
    
    return send_file(export_path, as_attachment=True, download_name=filename)

if __name__ == "__main__":
    Timer(1.0, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, port=5000, host='0.0.0.0')
"
import os, sys, webbrowser, subprocess, shutil
from pathlib import Path
from threading import Timer
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file
from ruamel.yaml import YAML
from werkzeug.utils import secure_filename

app = Flask(__name__)
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

def get_match_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "espanso" / "match"
    return Path.home() / ".config" / "espanso" / "match"

MATCH_DIR = get_match_dir()

def ensure_absolute_path(path_str):
    if sys.platform != "win32" and not path_str.startswith('/'):
        return '/' + path_str
    return path_str

def get_file_label(filepath):
    """Extract meaningful label - use parent folder name if file is named 'package.yml'"""
    path = Path(filepath)
    if path.stem.lower() == "package":
        return path.parent.name
    return path.stem

def load_snippets():
    snippets = []
    if not MATCH_DIR.exists():
        return snippets, False
    for f in MATCH_DIR.glob("**/*.yml"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.load(fp)
            if data and "matches" in data:
                for i, m in enumerate(data["matches"]):
                    is_markdown = False
                    entry_replace = ""

                    if "markdown" in m:
                        entry_replace = m["markdown"]
                        is_markdown = True
                    else:
                        entry_replace = m.get("replace", "")

                    if not isinstance(entry_replace, str):
                        entry_replace = str(entry_replace)

                    snippets.append({
                        "id": f"{f}::{i}",
                        "file": str(f),
                        "file_label": get_file_label(f),
                        "index": i,
                        "trigger": m.get("trigger", ""),
                        "replace": entry_replace,
                        "word": m.get("word", False),
                        "propagate_case": m.get("propagate_case", False),
                        "is_markdown": is_markdown
                    })
        except Exception as e:
            print(f"Error loading {f}: {e}")
    return snippets, True

def get_yaml_files():
    """Get list of all YAML files in match directory"""
    files = []
    if MATCH_DIR.exists():
        for f in MATCH_DIR.glob("**/*.yml"):
            files.append({
                "path": str(f),
                "label": get_file_label(f),
                "relative": str(f.relative_to(MATCH_DIR))
            })
    return sorted(files, key=lambda x: x["label"].lower())

def save_snippet(filepath, index, trigger, replace, word, pcase, is_markdown, is_new=False):
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            data = loaded if isinstance(loaded, dict) else {}

    if "matches" not in data:
        data["matches"] = []

    entry = {"trigger": trigger}

    if is_markdown:
        entry["markdown"] = replace
    else:
        entry["replace"] = replace

    if word: entry["word"] = True
    if pcase: entry["propagate_case"] = True

    if is_new:
        data["matches"].append(entry)
    else:
        if index < len(data["matches"]):
            orig = data["matches"][index]
            for k in orig:
                if k not in ["trigger", "replace", "markdown", "word", "propagate_case"]:
                    entry[k] = orig[k]
            data["matches"][index] = entry
        else:
            raise IndexError(f"Index {index} out of range.")

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

def delete_snippet(filepath, index):
    filepath = Path(filepath)
    if not filepath.exists(): return
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    if data and "matches" in data and index < len(data["matches"]):
        del data["matches"][index]
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f) if data["matches"] else f.write('')

def move_snippet(source_file, source_index, target_file):
    """Move a snippet from one file to another"""
    source_path = Path(source_file)
    target_path = Path(target_file)
    
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    # Load source file
    with open(source_path, "r", encoding="utf-8") as f:
        source_data = yaml.load(f)
    
    if not source_data or "matches" not in source_data:
        raise ValueError("Source file has no matches")
    
    if source_index >= len(source_data["matches"]):
        raise IndexError(f"Index {source_index} out of range")
    
    # Get the snippet to move
    snippet = source_data["matches"][source_index]
    
    # Load or create target file
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_data = {}
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            target_data = loaded if isinstance(loaded, dict) else {}
    
    if "matches" not in target_data:
        target_data["matches"] = []
    
    # Add to target
    target_data["matches"].append(snippet)
    
    # Remove from source
    del source_data["matches"][source_index]
    
    # Save both files
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump(target_data, f)
    
    with open(source_path, "w", encoding="utf-8") as f:
        if source_data["matches"]:
            yaml.dump(source_data, f)
        else:
            f.write('')

def copy_snippets_to_file(snippet_ids, target_file):
    """Copy multiple snippets to a target file (for export)"""
    target_path = Path(target_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    target_data = {"matches": []}
    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = yaml.load(f)
            if loaded and "matches" in loaded:
                target_data = loaded
    
    snippets, _ = load_snippets()
    snippets_by_id = {s["id"]: s for s in snippets}
    
    for sid in snippet_ids:
        if sid in snippets_by_id:
            s = snippets_by_id[sid]
            # Load original entry from file to preserve all fields
            source_path = Path(s["file"])
            with open(source_path, "r", encoding="utf-8") as f:
                source_data = yaml.load(f)
            if source_data and "matches" in source_data and s["index"] < len(source_data["matches"]):
                entry = source_data["matches"][s["index"]]
                target_data["matches"].append(entry)
    
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump(target_data, f)
    
    return len(snippet_ids)

def import_yaml_file(source_path, merge_into=None):
    """Import a YAML file into Espanso match directory"""
    source_path = Path(source_path)
    
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")
    
    # Validate it's a valid Espanso file
    with open(source_path, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    
    if not data or "matches" not in data:
        raise ValueError("Invalid Espanso file: no 'matches' key found")
    
    if merge_into:
        # Merge into existing file
        target_path = Path(merge_into)
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                target_data = yaml.load(f)
            if target_data and "matches" in target_data:
                target_data["matches"].extend(data["matches"])
            else:
                target_data = data
        else:
            target_data = data
        
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(target_data, f)
        
        return len(data["matches"]), target_path
    else:
        # Copy as new file
        target_name = source_path.stem
        target_path = MATCH_DIR / f"{target_name}.yml"
        
        # Avoid overwriting
        counter = 1
        while target_path.exists():
            target_path = MATCH_DIR / f"{target_name}_{counter}.yml"
            counter += 1
        
        shutil.copy(source_path, target_path)
        return len(data["matches"]), target_path

def create_new_file(filename):
    """Create a new empty YAML file"""
    if not filename.endswith('.yml'):
        filename += '.yml'
    
    # Sanitize filename
    filename = secure_filename(filename)
    filepath = MATCH_DIR / filename
    
    if filepath.exists():
        raise FileExistsError(f"File already exists: {filename}")
    
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Create empty matches file
    data = {"matches": []}
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    
    return filepath

def open_folder(folder_path):
    """Open the folder in the system file manager"""
    folder_path = Path(folder_path)
    if not folder_path.exists():
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(['explorer', str(folder_path)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(['open', str(folder_path)], check=False)
        else:
            subprocess.run(['xdg-open', str(folder_path)], check=False)
        return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False

TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SnippetMaster</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root {
    --bg-primary: #0d0d14;
    --bg-secondary: #16161f;
    --bg-card: #1e1e2a;
    --bg-card-hover: #262636;
    --text-primary: #e8e8ed;
    --text-secondary: #8b8b9e;
    --text-muted: #5a5a6e;
    --accent-blue: #3b82f6;
    --accent-blue-hover: #2563eb;
    --accent-green: #22c55e;
    --accent-green-hover: #16a34a;
    --accent-red: #ef4444;
    --accent-red-hover: #dc2626;
    --accent-purple: #a855f7;
    --accent-purple-hover: #9333ea;
    --border-color: #2a2a3a;
    --badge-bg: #2a2a3a;
    --badge-text: #a0a0b8;
    --badge-yellow-bg: #422006;
    --badge-yellow-text: #fbbf24;
    --badge-blue-bg: #172554;
    --badge-blue-text: #60a5fa;
    --shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    --radius: 8px;
    --radius-lg: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.5;
}

.container { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 24px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-color);
}

.header-left { display: flex; align-items: baseline; gap: 12px; }

.logo {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

.logo:hover { color: var(--accent-blue); }

.snippet-count { font-size: 0.95rem; color: var(--text-secondary); font-weight: 400; }

.header-right { display: flex; align-items: center; gap: 12px; }

.search-container { position: relative; }

.search-icon {
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
}

.search-input {
    width: 240px;
    padding: 10px 16px 10px 42px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    transition: all 0.2s ease;
}

.search-input::placeholder { color: var(--text-muted); }
.search-input:focus { outline: none; border-color: var(--accent-blue); background: var(--bg-card); }

.btn {
    padding: 10px 18px;
    border-radius: var(--radius);
    border: none;
    font-size: 0.9rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
}

.btn-primary { background: var(--accent-blue); color: white; }
.btn-primary:hover { background: var(--accent-blue-hover); transform: translateY(-1px); }

.btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-secondary:hover { background: var(--bg-card-hover); border-color: var(--text-muted); }

.btn-success { background: var(--accent-green); color: white; }
.btn-success:hover { background: var(--accent-green-hover); }

.btn-purple { background: var(--accent-purple); color: white; }
.btn-purple:hover { background: var(--accent-purple-hover); }

.btn-danger { background: var(--accent-red); color: white; }
.btn-danger:hover { background: var(--accent-red-hover); }

.btn-icon { width: 38px; height: 38px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); }

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.controls-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}

.control-select {
    padding: 10px 36px 10px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-family: inherit;
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238b8b9e' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    transition: all 0.2s ease;
}

.control-select:hover { border-color: var(--text-muted); }
.control-select:focus { outline: none; border-color: var(--accent-blue); }

.btn-folder { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); display: none; }
.btn-folder:hover { background: var(--bg-card-hover); border-color: var(--text-muted); }

.filtered-count { font-size: 0.9rem; color: var(--text-secondary); margin-left: auto; }

/* Selection Mode */
.selection-bar {
    display: none;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--accent-purple);
    border-radius: var(--radius);
    margin-bottom: 16px;
}

.selection-bar.active { display: flex; }

.selection-count { font-weight: 500; color: var(--accent-purple); }

.snippet-checkbox {
    width: 20px;
    height: 20px;
    accent-color: var(--accent-purple);
    cursor: pointer;
    margin-right: 12px;
    display: none;
}

.selection-mode .snippet-checkbox { display: block; }
.selection-mode .snippet-card { cursor: default; }
.selection-mode .snippet-card:hover { transform: none; }

#snippet-list { display: flex; flex-direction: column; gap: 10px; }

.snippet-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 16px 20px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: all 0.2s ease;
    position: relative;
}

.snippet-card:hover { background: var(--bg-card-hover); border-color: var(--text-muted); transform: translateX(2px); }
.snippet-card.selected { border-color: var(--accent-purple); background: rgba(168, 85, 247, 0.1); }

.snippet-content { flex: 1; min-width: 0; display: flex; align-items: center; }
.snippet-info { flex: 1; min-width: 0; }

.snippet-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }

.snippet-trigger { font-family: 'JetBrains Mono', monospace; font-weight: 500; font-size: 1rem; color: var(--accent-blue); }

.badge { padding: 3px 8px; font-size: 0.75rem; font-weight: 500; border-radius: 4px; background: var(--badge-bg); color: var(--badge-text); }
.badge-file { background: var(--badge-bg); color: var(--badge-text); }
.badge-word { background: var(--badge-bg); color: var(--badge-text); }
.badge-case { background: var(--badge-bg); color: var(--badge-text); }
.badge-md { background: var(--badge-blue-bg); color: var(--badge-blue-text); }

.snippet-preview { font-size: 0.9rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 600px; }

.snippet-actions { display: flex; gap: 8px; opacity: 0; transition: opacity 0.2s ease; }
.snippet-card:hover .snippet-actions { opacity: 1; }

.btn-edit { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color); }
.btn-edit:hover { background: var(--accent-blue); border-color: var(--accent-blue); }

.btn-delete { background: var(--accent-red); color: white; }
.btn-delete:hover { background: var(--accent-red-hover); }

.message {
    padding: 14px 18px;
    border-radius: var(--radius);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 500;
}

.message-success { background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); color: var(--accent-green); }
.message-error { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--accent-red); }

.empty-state { text-align: center; padding: 80px 20px; color: var(--text-secondary); }
.empty-state h2 { font-size: 1.5rem; color: var(--text-primary); margin-bottom: 12px; }
.empty-state p { font-size: 1rem; }

.back-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.9rem;
    margin-bottom: 24px;
    transition: color 0.2s ease;
}

.back-link:hover { color: var(--accent-blue); }

.form-title { font-size: 1.75rem; font-weight: 600; margin-bottom: 32px; color: var(--text-primary); }

.form-group { margin-bottom: 24px; }

.form-label { display: block; font-size: 0.9rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 8px; }

.form-input, .form-textarea {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-size: 0.95rem;
    font-family: inherit;
    transition: all 0.2s ease;
}

.form-textarea { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; resize: vertical; min-height: 200px; }

.form-input:focus, .form-textarea:focus { outline: none; border-color: var(--accent-blue); background: var(--bg-card); }
.form-input::placeholder, .form-textarea::placeholder { color: var(--text-muted); }

.options-box { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 16px 20px; }

.option-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
.option-item:not(:last-child) { border-bottom: 1px solid var(--border-color); }
.option-item input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--accent-blue); cursor: pointer; }
.option-item label { font-size: 0.9rem; color: var(--text-primary); cursor: pointer; }

.form-actions { margin-top: 32px; display: flex; gap: 12px; }

/* Modal */
.modal-overlay {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    z-index: 1000;
    align-items: center;
    justify-content: center;
}

.modal-overlay.active { display: flex; }

.modal {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
}

.modal-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 20px; }

.modal-actions { display: flex; gap: 12px; margin-top: 24px; justify-content: flex-end; }

/* File list in modal */
.file-list { max-height: 300px; overflow-y: auto; margin: 16px 0; }

.file-item {
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    margin-bottom: 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 10px;
}

.file-item:hover { border-color: var(--accent-blue); background: var(--bg-card-hover); }
.file-item.selected { border-color: var(--accent-purple); background: rgba(168, 85, 247, 0.15); }

.file-item-label { font-weight: 500; }
.file-item-path { font-size: 0.8rem; color: var(--text-muted); }

/* File input styling */
.file-input-wrapper { position: relative; }

.file-input-wrapper input[type="file"] {
    position: absolute;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
}

.file-input-label {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 40px 20px;
    background: var(--bg-secondary);
    border: 2px dashed var(--border-color);
    border-radius: var(--radius);
    color: var(--text-secondary);
    transition: all 0.2s ease;
}

.file-input-wrapper:hover .file-input-label { border-color: var(--accent-blue); color: var(--accent-blue); }

.selected-file { margin-top: 12px; padding: 10px 14px; background: var(--bg-secondary); border-radius: var(--radius); font-size: 0.9rem; }

/* Dropdown menu */
.dropdown { position: relative; }

.dropdown-menu {
    display: none;
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    min-width: 180px;
    z-index: 100;
    box-shadow: var(--shadow);
}

.dropdown-menu.active { display: block; }

.dropdown-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    color: var(--text-primary);
    text-decoration: none;
    transition: background 0.2s ease;
    cursor: pointer;
    border: none;
    background: none;
    width: 100%;
    font-size: 0.9rem;
    font-family: inherit;
}

.dropdown-item:hover { background: var(--bg-card-hover); }
.dropdown-item:first-child { border-radius: var(--radius) var(--radius) 0 0; }
.dropdown-item:last-child { border-radius: 0 0 var(--radius) var(--radius); }

.dropdown-divider { height: 1px; background: var(--border-color); margin: 4px 0; }

@media (max-width: 768px) {
    .container { padding: 16px; }
    header { flex-direction: column; gap: 16px; align-items: flex-start; }
    .header-right { width: 100%; flex-direction: column; align-items: stretch; }
    .search-input { width: 100%; }
    .controls-bar { flex-direction: column; align-items: stretch; }
    .control-select { width: 100%; }
    .filtered-count { margin-left: 0; text-align: center; }
    .snippet-actions { opacity: 1; }
    .snippet-preview { max-width: 100%; }
}
</style>
</head>
<body>
<div class="container">
<header>
<div class="header-left">
    <a href="/" class="logo">
        <span>⌨</span>
        <span>SnippetMaster</span>
    </a>
    {% if snippet_count is defined %}<span class="snippet-count">({{ snippet_count }} snippet{{ 's' if snippet_count != 1 else '' }})</span>{% endif %}
</div>
{% if view != 'error' %}
<div class="header-right">
    <div class="search-container">
        <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
        </svg>
        <input type="text" id="search-input" class="search-input" placeholder="Search">
    </div>
    <a href="/new" class="btn btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5v14M5 12h14"/>
        </svg>
        Add New
    </a>
    <div class="dropdown">
        <button class="btn btn-secondary" id="menu-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="1"></circle>
                <circle cx="12" cy="5" r="1"></circle>
                <circle cx="12" cy="19" r="1"></circle>
            </svg>
            More
        </button>
        <div class="dropdown-menu" id="menu-dropdown">
            <button class="dropdown-item" onclick="openModal('new-file-modal')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="12" y1="18" x2="12" y2="12"></line>
                    <line x1="9" y1="15" x2="15" y2="15"></line>
                </svg>
                New Collection
            </button>
            <button class="dropdown-item" onclick="openModal('import-modal')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                Import Collection
            </button>
            <div class="dropdown-divider"></div>
            <button class="dropdown-item" id="toggle-selection-btn" onclick="toggleSelectionMode()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 11 12 14 22 4"></polyline>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                </svg>
                Select Snippets
            </button>
            <div class="dropdown-divider"></div>
            <button class="dropdown-item" onclick="openMatchDir()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
                Open Espanso Folder
            </button>
        </div>
    </div>
</div>
{% endif %}
</header>

<main>
{% if msg %}
<div class="message {{ 'message-success' if mt == 'success' else 'message-error' }}">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        {% if mt == 'success' %}
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
        {% else %}
        <circle cx="12" cy="12" r="10"></circle>
        <path d="m15 9-6 6M9 9l6 6"/>
        {% endif %}
    </svg>
    <span>{{ msg }}</span>
</div>
{% endif %}

{% if view == 'list' %}
    <!-- Selection Bar -->
    <div class="selection-bar" id="selection-bar">
        <span class="selection-count"><span id="selected-count">0</span> selected</span>
        <button class="btn btn-sm btn-purple" onclick="openMoveModal()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            Move to...
        </button>
        <button class="btn btn-sm btn-success" onclick="openExportModal()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            Export...
        </button>
        <button class="btn btn-sm btn-secondary" onclick="toggleSelectionMode()">Cancel</button>
    </div>

    {% if snippets %}
    <div class="controls-bar">
        <select id="filter-file" class="control-select">
            <option value="all">Collection: All files</option>
            {% for file in unique_files %}
            <option value="{{ file.path }}">Collection: {{ file.label }}</option>
            {% endfor %}
        </select>
        <select id="sort-order" class="control-select">
            <option value="asc">Sort: A → Z</option>
            <option value="desc">Sort: Z → A</option>
        </select>
        <button id="btn-open-folder" class="btn btn-folder" title="Open folder in file manager">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
            Open Folder
        </button>
        <span id="filtered-count" class="filtered-count"></span>
    </div>

    <div id="snippet-list">
        {% for s in snippets %}
        <div class="snippet-card" data-file="{{ s.file }}" data-trigger="{{ s.trigger|lower }}" data-id="{{ s.id|urlencode }}">
            <div class="snippet-content">
                <input type="checkbox" class="snippet-checkbox" data-id="{{ s.id|urlencode }}" onclick="event.stopPropagation(); updateSelectionCount();">
                <div class="snippet-info">
                    <div class="snippet-header">
                        <span class="snippet-trigger">{{ s.trigger }}</span>
                        <span class="badge badge-file">{{ s.file_label }}</span>
                        {% if s.word %}<span class="badge badge-word">word</span>{% endif %}
                        {% if s.propagate_case %}<span class="badge badge-case">case</span>{% endif %}
                        {% if s.is_markdown %}<span class="badge badge-md">md</span>{% endif %}
                    </div>
                    <div class="snippet-preview">Expansion: {{ s.replace.split('\n')[0][:80] }}</div>
                </div>
            </div>
            <div class="snippet-actions">
                <a href="/edit/{{ s.id|urlencode }}" class="btn btn-icon btn-edit" onclick="event.stopPropagation();" title="Edit">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                </a>
                <a href="/delete/{{ s.id|urlencode }}" class="btn btn-icon btn-delete" onclick="event.stopPropagation();" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </a>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
        <div class="empty-state">
            <h2>No snippets yet</h2>
            <p>Click <strong>+ Add New</strong> to create your first snippet, or import an existing collection.</p>
        </div>
    {% endif %}

<!-- New File Modal -->
<div class="modal-overlay" id="new-file-modal">
    <div class="modal">
        <h2 class="modal-title">Create New Collection</h2>
        <form id="new-file-form" action="/create-file" method="POST">
            <div class="form-group">
                <label class="form-label" for="new-filename">Collection Name</label>
                <input type="text" id="new-filename" name="filename" class="form-input" placeholder="my-snippets" required>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">.yml extension will be added automatically</p>
            </div>
            <div class="modal-actions">
                <button type="button" class="btn btn-secondary" onclick="closeModal('new-file-modal')">Cancel</button>
                <button type="submit" class="btn btn-primary">Create</button>
            </div>
        </form>
    </div>
</div>

<!-- Import Modal -->
<div class="modal-overlay" id="import-modal">
    <div class="modal">
        <h2 class="modal-title">Import Collection</h2>
        <form id="import-form" action="/import" method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label class="form-label">Select YAML file</label>
                <div class="file-input-wrapper">
                    <input type="file" id="import-file" name="file" accept=".yml,.yaml" required onchange="updateFileLabel(this)">
                    <div class="file-input-label">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        <span>Click to select or drag and drop</span>
                    </div>
                </div>
                <div id="selected-file-name" class="selected-file" style="display: none;"></div>
            </div>
            <div class="form-group">
                <label class="form-label">Import as</label>
                <div class="option-item" style="padding: 0;">
                    <input type="radio" id="import-new" name="import_mode" value="new" checked>
                    <label for="import-new">New collection (keep original filename)</label>
                </div>
                <div class="option-item" style="border: none;">
                    <input type="radio" id="import-merge" name="import_mode" value="merge">
                    <label for="import-merge">Merge into existing collection</label>
                </div>
                <select id="merge-target" name="merge_target" class="control-select" style="width: 100%; margin-top: 8px; display: none;">
                    {% for file in unique_files %}
                    <option value="{{ file.path }}">{{ file.label }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="modal-actions">
                <button type="button" class="btn btn-secondary" onclick="closeModal('import-modal')">Cancel</button>
                <button type="submit" class="btn btn-success">Import</button>
            </div>
        </form>
    </div>
</div>

<!-- Move Modal -->
<div class="modal-overlay" id="move-modal">
    <div class="modal">
        <h2 class="modal-title">Move Snippets</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">Select destination collection:</p>
        <div class="file-list" id="move-file-list">
            {% for file in unique_files %}
            <div class="file-item" data-path="{{ file.path }}" onclick="selectMoveTarget(this)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <div>
                    <div class="file-item-label">{{ file.label }}</div>
                    <div class="file-item-path">{{ file.relative }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        <div style="margin-top: 12px;">
            <button class="btn btn-sm btn-secondary" onclick="showNewFileInMove()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 5v14M5 12h14"/>
                </svg>
                Create new collection
            </button>
        </div>
        <div id="move-new-file" style="display: none; margin-top: 12px;">
            <input type="text" id="move-new-filename" class="form-input" placeholder="new-collection-name">
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" onclick="closeModal('move-modal')">Cancel</button>
            <button type="button" class="btn btn-purple" id="move-confirm-btn" onclick="confirmMove()">Move</button>
        </div>
    </div>
</div>

<!-- Export Modal -->
<div class="modal-overlay" id="export-modal">
    <div class="modal">
        <h2 class="modal-title">Export Snippets</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">Export selected snippets to a new file for sharing.</p>
        <div class="form-group">
            <label class="form-label" for="export-filename">Export filename</label>
            <input type="text" id="export-filename" class="form-input" placeholder="shared-snippets" value="shared-snippets">
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px;">.yml extension will be added automatically</p>
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" onclick="closeModal('export-modal')">Cancel</button>
            <button type="button" class="btn btn-success" onclick="confirmExport()">Export & Download</button>
        </div>
    </div>
</div>

<script>
(function() {
    const filterSelect = document.getElementById('filter-file');
    const sortSelect = document.getElementById('sort-order');
    const openFolderBtn = document.getElementById('btn-open-folder');
    const filteredCountSpan = document.getElementById('filtered-count');
    const snippetList = document.getElementById('snippet-list');
    const searchInput = document.getElementById('search-input');
    const cards = snippetList ? Array.from(snippetList.querySelectorAll('.snippet-card')) : [];
    const menuBtn = document.getElementById('menu-btn');
    const menuDropdown = document.getElementById('menu-dropdown');

    let searchQuery = '';
    let selectionMode = false;

    // Dropdown menu
    if (menuBtn) {
        menuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            menuDropdown.classList.toggle('active');
        });
        document.addEventListener('click', () => menuDropdown.classList.remove('active'));
    }

    // Click handler for cards
    cards.forEach(card => {
        card.addEventListener('click', function(e) {
            if (selectionMode) {
                const checkbox = this.querySelector('.snippet-checkbox');
                checkbox.checked = !checkbox.checked;
                this.classList.toggle('selected', checkbox.checked);
                updateSelectionCount();
            } else if (!e.target.closest('.snippet-actions')) {
                location.href = '/edit/' + this.dataset.id;
            }
        });
    });

    function applyFilterAndSort() {
        if (!filterSelect || !sortSelect) return;
        
        const filterValue = filterSelect.value;
        const sortValue = sortSelect.value;

        if (openFolderBtn) {
            if (filterValue === 'all') {
                openFolderBtn.style.display = 'none';
            } else {
                openFolderBtn.style.display = 'inline-flex';
                openFolderBtn.dataset.filepath = filterValue;
            }
        }

        let visibleCards = cards.filter(card => {
            const matchesFile = filterValue === 'all' || card.dataset.file === filterValue;
            const matchesSearch = !searchQuery ||
                card.dataset.trigger.includes(searchQuery.toLowerCase()) ||
                card.querySelector('.snippet-preview').textContent.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesFile && matchesSearch;
        });

        visibleCards.sort((a, b) => {
            const triggerA = a.dataset.trigger;
            const triggerB = b.dataset.trigger;
            return sortValue === 'asc' ? triggerA.localeCompare(triggerB) : triggerB.localeCompare(triggerA);
        });

        cards.forEach(card => card.style.display = 'none');
        visibleCards.forEach(card => {
            card.style.display = 'flex';
            snippetList.appendChild(card);
        });

        const total = cards.length;
        const visible = visibleCards.length;
        if (filteredCountSpan) {
            filteredCountSpan.textContent = (filterValue === 'all' && !searchQuery) ? '' : `Showing ${visible} of ${total}`;
        }
    }

    if (filterSelect) filterSelect.addEventListener('change', applyFilterAndSort);
    if (sortSelect) sortSelect.addEventListener('change', applyFilterAndSort);
    if (searchInput) searchInput.addEventListener('input', function() { searchQuery = this.value; applyFilterAndSort(); });

    if (openFolderBtn) {
        openFolderBtn.addEventListener('click', function() {
            const filepath = this.dataset.filepath;
            if (filepath) {
                fetch('/open-folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filepath: filepath })
                }).then(r => r.json()).then(data => {
                    if (!data.success) alert('Could not open folder: ' + (data.error || 'Unknown error'));
                }).catch(() => alert('Error opening folder'));
            }
        });
    }

    applyFilterAndSort();

    // Selection mode
    window.toggleSelectionMode = function() {
        selectionMode = !selectionMode;
        document.body.classList.toggle('selection-mode', selectionMode);
        document.getElementById('selection-bar').classList.toggle('active', selectionMode);
        document.getElementById('toggle-selection-btn').innerHTML = selectionMode ? 
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg> Cancel Selection' :
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg> Select Snippets';
        
        if (!selectionMode) {
            document.querySelectorAll('.snippet-checkbox').forEach(cb => cb.checked = false);
            document.querySelectorAll('.snippet-card').forEach(card => card.classList.remove('selected'));
            updateSelectionCount();
        }
        menuDropdown.classList.remove('active');
    };

    window.updateSelectionCount = function() {
        const count = document.querySelectorAll('.snippet-checkbox:checked').length;
        document.getElementById('selected-count').textContent = count;
    };

    // Modals
    window.openModal = function(id) {
        document.getElementById(id).classList.add('active');
        menuDropdown.classList.remove('active');
    };

    window.closeModal = function(id) {
        document.getElementById(id).classList.remove('active');
    };

    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', function(e) {
            if (e.target === this) this.classList.remove('active');
        });
    });

    // Import modal - toggle merge target
    document.querySelectorAll('input[name="import_mode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            document.getElementById('merge-target').style.display = this.value === 'merge' ? 'block' : 'none';
        });
    });

    window.updateFileLabel = function(input) {
        const fileName = input.files[0]?.name;
        const display = document.getElementById('selected-file-name');
        if (fileName) {
            display.textContent = 'Selected: ' + fileName;
            display.style.display = 'block';
        } else {
            display.style.display = 'none';
        }
    };

    // Move modal
    let selectedMoveTarget = null;
    let createNewInMove = false;

    window.openMoveModal = function() {
        selectedMoveTarget = null;
        createNewInMove = false;
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        document.getElementById('move-new-file').style.display = 'none';
        document.getElementById('move-new-filename').value = '';
        openModal('move-modal');
    };

    window.selectMoveTarget = function(el) {
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        el.classList.add('selected');
        selectedMoveTarget = el.dataset.path;
        createNewInMove = false;
        document.getElementById('move-new-file').style.display = 'none';
    };

    window.showNewFileInMove = function() {
        document.querySelectorAll('#move-file-list .file-item').forEach(item => item.classList.remove('selected'));
        selectedMoveTarget = null;
        createNewInMove = true;
        document.getElementById('move-new-file').style.display = 'block';
        document.getElementById('move-new-filename').focus();
    };

    window.confirmMove = function() {
        const selected = Array.from(document.querySelectorAll('.snippet-checkbox:checked')).map(cb => cb.dataset.id);
        if (selected.length === 0) { alert('No snippets selected'); return; }

        let targetFile = selectedMoveTarget;
        if (createNewInMove) {
            const newName = document.getElementById('move-new-filename').value.trim();
            if (!newName) { alert('Please enter a collection name'); return; }
            targetFile = '_new_:' + newName;
        }

        if (!targetFile) { alert('Please select a destination'); return; }

        fetch('/move-snippets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ snippets: selected, target: targetFile })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                location.href = '/?msg=' + encodeURIComponent(data.message) + '&mt=success';
            } else {
                alert('Error: ' + data.error);
            }
        }).catch(err => alert('Error moving snippets'));
    };

    // Export modal
    window.openExportModal = function() {
        const count = document.querySelectorAll('.snippet-checkbox:checked').length;
        if (count === 0) { alert('No snippets selected'); return; }
        document.getElementById('export-filename').value = 'shared-snippets';
        openModal('export-modal');
    };

    window.confirmExport = function() {
        const selected = Array.from(document.querySelectorAll('.snippet-checkbox:checked')).map(cb => cb.dataset.id);
        const filename = document.getElementById('export-filename').value.trim() || 'shared-snippets';

        fetch('/export-snippets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ snippets: selected, filename: filename })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                // Trigger download
                window.location.href = '/download-export/' + encodeURIComponent(data.filename);
                closeModal('export-modal');
                toggleSelectionMode();
            } else {
                alert('Error: ' + data.error);
            }
        }).catch(err => alert('Error exporting snippets'));
    };

    window.openMatchDir = function() {
        fetch('/open-match-dir', { method: 'POST' })
            .then(r => r.json())
            .then(data => { if (!data.success) alert('Could not open folder'); })
            .catch(() => alert('Error opening folder'));
        menuDropdown.classList.remove('active');
    };
})();
</script>

{% elif view == 'edit' or view == 'new' %}
    <a href="/" class="back-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m15 18-6-6 6-6"/>
        </svg>
        Back to list
    </a>
    <h1 class="form-title">{{ 'Edit Snippet' if view == 'edit' else 'Add New Snippet' }}</h1>
    <form method="POST" action="{{ '/update/' + (snippet.id|urlencode) if view == 'edit' else '/create' }}">
        {% if view == 'new' %}
        <div class="form-group">
            <label class="form-label" for="target_file">Save to Collection</label>
            <select id="target_file" name="target_file" class="control-select" style="width: 100%;">
                <option value="">Default (base.yml)</option>
                {% for file in unique_files %}
                <option value="{{ file.path }}">{{ file.label }}</option>
                {% endfor %}
            </select>
        </div>
        {% endif %}
        <div class="form-group">
            <label class="form-label" for="trigger">Trigger</label>
            <input type="text" id="trigger" name="trigger" class="form-input" value="{{ snippet.trigger if snippet else '' }}" placeholder=":trigger">
        </div>
        <div class="form-group">
            <label class="form-label" for="replace">Replacement</label>
            <textarea id="replace" name="replace" class="form-textarea" rows="10">{{ snippet.replace if snippet else '' }}</textarea>
        </div>
        <div class="form-group">
            <label class="form-label">Options</label>
            <div class="options-box">
                <div class="option-item">
                    <input type="checkbox" id="word" name="word" {{ 'checked' if snippet and snippet.word else '' }}>
                    <label for="word">Expand only if a whole word</label>
                </div>
                <div class="option-item">
                    <input type="checkbox" id="propagate_case" name="propagate_case" {{ 'checked' if snippet and snippet.propagate_case else '' }}>
                    <label for="propagate_case">Propagate case</label>
                </div>
                <div class="option-item">
                    <input type="checkbox" id="markdown" name="markdown" {{ 'checked' if snippet and snippet.is_markdown else '' }}>
                    <label for="markdown">Paste as Markdown</label>
                </div>
            </div>
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
                    <polyline points="17 21 17 13 7 13 7 21"></polyline>
                    <polyline points="7 3 7 8 15 8"></polyline>
                </svg>
                {{ 'Save Changes' if view == 'edit' else 'Create Snippet' }}
            </button>
            <a href="/" class="btn btn-secondary">Cancel</a>
        </div>
    </form>
{% endif %}
</main>
</div>
</body>
</html>'''

@app.route("/")
def index():
    snippets, exists = load_snippets()
    if not exists: return "Espanso match dir not found"

    unique_files_dict = {}
    for s in snippets:
        if s["file"] not in unique_files_dict:
            unique_files_dict[s["file"]] = s["file_label"]

    unique_files = [{"path": path, "label": label, "relative": str(Path(path).relative_to(MATCH_DIR)) if Path(path).is_relative_to(MATCH_DIR) else path} 
                    for path, label in sorted(unique_files_dict.items(), key=lambda x: x[1].lower())]

    return render_template_string(TEMPLATE, view="list", snippets=snippets,
                                  snippet_count=len(snippets),
                                  unique_files=unique_files,
                                  msg=request.args.get("msg"), mt=request.args.get("mt"))

@app.route("/new")
def new_snippet():
    unique_files = get_yaml_files()
    return render_template_string(TEMPLATE, view="new", snippet=None, unique_files=unique_files)

@app.route("/edit/<path:snippet_id>")
def edit_snippet(snippet_id):
    snippets, _ = load_snippets()
    full_id = ensure_absolute_path(snippet_id)
    snippet = next((s for s in snippets if s["id"] == full_id), None)
    if not snippet: snippet = next((s for s in snippets if s["id"] == snippet_id), None)
    return render_template_string(TEMPLATE, view="edit", snippet=snippet, unique_files=[])

@app.route("/create", methods=["POST"])
def create():
    try:
        target_file = request.form.get("target_file", "").strip()
        if not target_file:
            target_file = MATCH_DIR / "base.yml"
        else:
            target_file = Path(target_file)
        
        save_snippet(target_file, 0, request.form.get("trigger").strip(),
                     request.form.get("replace"), "word" in request.form,
                     "propagate_case" in request.form, "markdown" in request.form, is_new=True)
        return redirect(url_for("index", msg="Created", mt="success"))
    except Exception as e: return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/update/<path:snippet_id>", methods=["POST"])
def update(snippet_id):
    try:
        filepath, index = ensure_absolute_path(snippet_id).rsplit("::", 1)
        save_snippet(filepath, int(index), request.form.get("trigger").strip(),
                     request.form.get("replace"), "word" in request.form,
                     "propagate_case" in request.form, "markdown" in request.form)
        return redirect(url_for("index", msg="Saved", mt="success"))
    except Exception as e: return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/delete/<path:snippet_id>")
def delete(snippet_id):
    filepath, index = ensure_absolute_path(snippet_id).rsplit("::", 1)
    delete_snippet(filepath, int(index))
    return redirect(url_for("index", msg="Deleted", mt="success"))

@app.route("/open-folder", methods=["POST"])
def open_folder_route():
    try:
        data = request.get_json()
        filepath = data.get("filepath", "")
        if not filepath:
            return jsonify({"success": False, "error": "No filepath provided"})
        folder_path = Path(filepath).parent
        success = open_folder(folder_path)
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/open-match-dir", methods=["POST"])
def open_match_dir_route():
    success = open_folder(MATCH_DIR)
    return jsonify({"success": success})

@app.route("/create-file", methods=["POST"])
def create_file_route():
    try:
        filename = request.form.get("filename", "").strip()
        if not filename:
            return redirect(url_for("index", msg="Filename required", mt="error"))
        
        filepath = create_new_file(filename)
        return redirect(url_for("index", msg=f"Created collection: {filepath.stem}", mt="success"))
    except FileExistsError as e:
        return redirect(url_for("index", msg=str(e), mt="error"))
    except Exception as e:
        return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/import", methods=["POST"])
def import_route():
    try:
        if 'file' not in request.files:
            return redirect(url_for("index", msg="No file selected", mt="error"))
        
        file = request.files['file']
        if file.filename == '':
            return redirect(url_for("index", msg="No file selected", mt="error"))
        
        # Save uploaded file temporarily
        temp_path = Path("/tmp") / secure_filename(file.filename)
        file.save(temp_path)
        
        import_mode = request.form.get("import_mode", "new")
        merge_target = request.form.get("merge_target") if import_mode == "merge" else None
        
        count, target_path = import_yaml_file(temp_path, merge_target)
        
        # Clean up temp file
        temp_path.unlink()
        
        action = "merged into" if merge_target else "imported as"
        return redirect(url_for("index", msg=f"Imported {count} snippets {action} {target_path.stem}", mt="success"))
    except Exception as e:
        return redirect(url_for("index", msg=str(e), mt="error"))

@app.route("/move-snippets", methods=["POST"])
def move_snippets_route():
    try:
        data = request.get_json()
        snippet_ids = data.get("snippets", [])
        target = data.get("target", "")
        
        if not snippet_ids:
            return jsonify({"success": False, "error": "No snippets selected"})
        
        if not target:
            return jsonify({"success": False, "error": "No target selected"})
        
        # Check if creating new file
        if target.startswith("_new_:"):
            new_name = target[6:]
            target_path = create_new_file(new_name)
        else:
            target_path = Path(target)
        
        # Decode snippet IDs and move them (in reverse order to handle index shifting)
        from urllib.parse import unquote
        decoded_ids = [unquote(sid) for sid in snippet_ids]
        
        # Group by file and sort by index descending
        by_file = {}
        for sid in decoded_ids:
            sid = ensure_absolute_path(sid)
            filepath, index = sid.rsplit("::", 1)
            if filepath not in by_file:
                by_file[filepath] = []
            by_file[filepath].append(int(index))
        
        # Sort indices in descending order to avoid index shifting issues
        moved_count = 0
        for filepath, indices in by_file.items():
            for index in sorted(indices, reverse=True):
                if Path(filepath) != target_path:  # Don't move to same file
                    move_snippet(filepath, index, target_path)
                    moved_count += 1
        
        return jsonify({"success": True, "message": f"Moved {moved_count} snippet(s) to {target_path.stem}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/export-snippets", methods=["POST"])
def export_snippets_route():
    try:
        data = request.get_json()
        snippet_ids = data.get("snippets", [])
        filename = data.get("filename", "export")
        
        if not snippet_ids:
            return jsonify({"success": False, "error": "No snippets selected"})
        
        # Decode snippet IDs
        from urllib.parse import unquote
        decoded_ids = [ensure_absolute_path(unquote(sid)) for sid in snippet_ids]
        
        # Create export file in temp directory
        if not filename.endswith('.yml'):
            filename += '.yml'
        export_path = Path("/tmp") / secure_filename(filename)
        
        count = copy_snippets_to_file(decoded_ids, export_path)
        
        return jsonify({"success": True, "filename": export_path.name, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/download-export/<filename>")
def download_export(filename):
    export_path = Path("/tmp") / secure_filename(filename)
    if not export_path.exists():
        return redirect(url_for("index", msg="Export file not found", mt="error"))
    
    return send_file(export_path, as_attachment=True, download_name=filename)

if __name__ == "__main__":
    Timer(1.0, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, port=5000, host='0.0.0.0')
