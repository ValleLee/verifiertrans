"""Deterministically retain P2P test state from the source test patch.

The source patch is a physical artifact, not a semantic contract.  This small
diff slicer uses resolved selector files and hunk-local test titles.  It keeps
shared setup/fixture hunks, removes files that are only selected by historical
F2P, and removes a F2P-only test hunk when its title is identifiable.  Every
decision is returned as accounting for package review.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _selectors(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key) or {}
    return [str(item) for item in (value.get("resolved") or [])] if isinstance(value, dict) else []


def _selector_info(values: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    files: set[str] = set()
    titles: dict[str, set[str]] = {}
    for value in values:
        file, marker, title = value.partition("::")
        file = file.split("|", 1)[0].strip()
        title = title.strip()
        if not marker or not file:
            continue
        files.add(file)
        titles.setdefault(file, set()).add(title)
    return files, titles


def _sections(patch: str) -> list[list[str]]:
    lines = patch.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    if not starts:
        return []
    return [lines[start:end] for start, end in zip(starts, starts[1:] + [len(lines)])]


def _path(section: list[str]) -> str | None:
    for line in section:
        if line.startswith("+++ b/"):
            return line[6:].strip()
    match = next((line for line in section if line.startswith("diff --git ")), "")
    parts = match.split()
    return parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else None


def _hunks(section: list[str]) -> tuple[list[str], list[list[str]]]:
    index = next((i for i, line in enumerate(section) if line.startswith("@@ ")), len(section))
    header = section[:index]
    starts = [i for i, line in enumerate(section[index:], start=index) if line.startswith("@@ ")]
    hunks = [section[start:end] for start, end in zip(starts, starts[1:] + [len(section)])]
    return header, hunks


def _remove_explicit_f2p_lines(hunk: list[str], f_titles: list[str], p_titles: list[str]) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    body: list[str] = []
    for line in hunk:
        if line.startswith("+") and not line.startswith("+++") and any(title in line for title in f_titles) and not any(title in line for title in p_titles):
            removed.append(line.rstrip("\n"))
            continue
        body.append(line)
    if not removed:
        return hunk, removed
    header = body[0]
    match = re.match(r"(@@ -\d+(?:,\d+)? \+\d+),(\d+)( @@.*\n?)$", header)
    if match:
        count = max(0, int(match.group(2)) - len(removed))
        body[0] = match.group(1) + "," + str(count) + match.group(3)
    return body, removed


def retain_p2p_test_patch(patch: str, selectors: dict[str, Any], repo: Path | None = None) -> tuple[str, dict[str, Any]]:
    f2p_files, f2p_titles = _selector_info(_selectors(selectors, "fail_to_pass"))
    p2p_files, p2p_titles = _selector_info(_selectors(selectors, "pass_to_pass"))
    retained: list[list[str]] = []
    report: dict[str, Any] = {
        "source_files": [], "retained_p2p_files": [], "retained_shared_files": [],
        "retained_fixture_files": [], "excluded_f2p_files": [], "excluded_f2p_hunks": [],
        "ambiguous_shared_hunks": [], "excluded_unreferenced_files": [],
        "source_patch_present": bool(str(patch).strip()),
    }
    selected_files = {str(item) for item in (selectors.get("selected_test_files_to_run") or [])}
    sections = _sections(patch)
    p2p_context = ""
    for section in sections:
        if _path(section) in p2p_files:
            p2p_context += "".join(section) + "\n"
    if repo is not None:
        for path in p2p_files:
            candidate = repo / path
            if candidate.is_file():
                p2p_context += candidate.read_text(encoding="utf-8", errors="ignore") + "\n"
    for section in sections:
        path = _path(section)
        if not path:
            continue
        report["source_files"].append(path)
        is_p2p = path in p2p_files
        is_f2p = path in f2p_files
        if is_f2p and not is_p2p:
            report["excluded_f2p_files"].append(path)
            continue
        if not is_p2p and not is_f2p:
            path_token = path.replace("\\", "/")
            basename = Path(path_token).name
            referenced = (
                path in selected_files
                or path_token in p2p_context
                or basename in p2p_context
            )
            if not referenced:
                report["excluded_unreferenced_files"].append(path)
                continue
        header, hunks = _hunks(section)
        selected: list[list[str]] = []
        for hunk in hunks:
            text = "".join(hunk)
            f_titles = [title for title in f2p_titles.get(path, set()) if title and title in text]
            p_titles = [title for title in p2p_titles.get(path, set()) if title and title in text]
            if f_titles and not p_titles:
                report["excluded_f2p_hunks"].append({"file": path, "titles": f_titles})
                continue
            if f_titles and p_titles:
                report["ambiguous_shared_hunks"].append({"file": path, "f2p": f_titles, "p2p": p_titles})
                hunk, removed = _remove_explicit_f2p_lines(hunk, f_titles, p_titles)
                if removed:
                    report["excluded_f2p_hunks"].append({"file": path, "titles": f_titles, "lines": removed})
                    if not any(line.startswith(("+", "-", " ")) for line in hunk[1:]):
                        continue
            selected.append(hunk)
        if not selected and hunks:
            continue
        if is_p2p:
            report["retained_p2p_files"].append(path)
            if is_f2p:
                report["retained_shared_files"].append(path)
        elif not is_f2p:
            report["retained_fixture_files"].append(path)
        retained.append(header + [line for hunk in selected for line in hunk])
    report["source_files"] = sorted(set(report["source_files"]))
    for key in ("retained_p2p_files", "retained_shared_files", "retained_fixture_files", "excluded_f2p_files", "excluded_unreferenced_files"):
        report[key] = sorted(set(report[key]))
    output = "".join(line for section in retained for line in section)
    return output, report
