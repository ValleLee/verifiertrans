"""Path-scoped tools shared by the model sessions.

The information boundary between roles is enforced here rather than in prompts:
a session's visible/writable roots are computed by its caller, and every tool
call is resolved against them. A session whose roots exclude ``sealed/`` cannot
open the gold patch by any path spelling, and the rejection is returned to the
agent as evidence rather than crashing the run.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List files below a visible workspace path.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file in the visible workspace.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": "Write a UTF-8 text file under a writable path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Run a shell command inside a visible workspace directory. Absolute paths and "
            "parent traversal are rejected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
            "required": ["command"],
        },
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
            "required": ["command"],
        },
    },
]

#: Directory names that must never be readable by a role, whatever its roots say.
#: Belt-and-braces: the roots already exclude them, but a mis-edited role config
#: should fail loudly rather than quietly expose the reference solution.
ALWAYS_HIDDEN = ("sealed",)
_ABSOLUTE_PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_/.])/(?!/|dev/null(?:\b|$))(?=[A-Za-z0-9_.-])"
)


def schemas(provider: str) -> list[dict[str, Any]]:
    key = "input_schema" if provider == "anthropic_compatible" else "parameters"
    return [{"name": item["name"], "description": item["description"], key: item[key]} for item in TOOL_SCHEMAS]


class WorkspaceTools:
    def __init__(
        self, root: Path, visible: list[str], writable: list[str], timeout: int = 120,
        readonly_shell: bool = False,
    ):
        self.root = root.resolve()
        self.visible = [(self.root / path).resolve() for path in visible]
        self.writable = [(self.root / path).resolve() for path in writable]
        self.timeout = timeout
        self.readonly_shell = readonly_shell

    @staticmethod
    def _under(path: Path, roots: list[Path]) -> bool:
        return any(path == root or root in path.parents for root in roots)

    @staticmethod
    def _touches_hidden(path: Path) -> bool:
        return any(part in ALWAYS_HIDDEN for part in path.parts)

    def _bash_default_root(self) -> Path:
        """Where a bare ``run_bash`` call runs.

        The first visible root that is not also a writable dir, so a restricted
        session lands in its evidence root and cannot enumerate siblings.
        """
        if not self.visible:
            return self.root
        for candidate in self.visible:
            if candidate.is_dir() and not self._touches_hidden(candidate):
                return candidate
        return self.root

    @staticmethod
    def _mask_quoted_heredoc_bodies(command: str) -> str:
        """Mask literal bodies of quoted heredocs before path-token checks.

        Converter scratch commands often embed source literals such as ``../src``
        or ``</script>`` in a single-quoted heredoc. Those are data, not shell
        paths. Only quoted heredocs are masked: an unquoted heredoc can expand
        substitutions, so its body remains subject to the normal safety checks.
        The heredoc header and delimiter are always retained and validated.
        """
        lines = command.splitlines(keepends=True)
        visible: list[str] = []
        skip_delimiter: str | None = None
        strip_tabs = False
        heredoc_re = re.compile(r"<<(?P<dash>-)?\s*(?P<quote>['\"]?)(?P<delim>[A-Za-z_][A-Za-z0-9_]*)\2")
        for line in lines:
            if skip_delimiter is not None:
                candidate = line.rstrip("\r\n")
                if strip_tabs:
                    candidate = candidate.lstrip("\t")
                if candidate == skip_delimiter:
                    visible.append(line)
                    skip_delimiter = None
                continue
            visible.append(line)
            match = heredoc_re.search(line)
            if match and match.group("quote"):
                skip_delimiter = match.group("delim")
                strip_tabs = bool(match.group("dash"))
                visible.append("__QUOTED_HEREDOC_BODY_MASKED__\n")
        return "".join(visible)

    def validate_bash(
        self, args: dict[str, Any], *, reject_hidden: bool = True,
    ) -> tuple[str, Path, int]:
        """Validate a shell action without executing it.

        A stronger runner can reuse these checks and execute the command in a
        separate sandbox rather than on the host process.
        """
        command = str(args["command"])
        checked_command = self._mask_quoted_heredoc_bodies(command)
        if ".." in checked_command or _ABSOLUTE_PATH_TOKEN.search(checked_command):
            raise PermissionError("run_bash rejects absolute paths and parent traversal")
        if self.readonly_shell and re.search(
            r"(?:^|[;&|])\s*(?:rm|mv|cp|mkdir|rmdir|touch|chmod|chown|ln|truncate)\b|"
            r"(?:git\s+(?:clean|reset|checkout|apply|switch))|"
            r"(?<!2)>{1,2}(?!&)|(?:\|\s*tee\b)|sed\s+-i",
            command,
        ):
            raise PermissionError("read-only role shell rejects filesystem mutation")
        if reject_hidden and any(hidden in command for hidden in ALWAYS_HIDDEN):
            raise PermissionError("run_bash may not touch sealed evidence")
        raw_cwd = str(args.get("cwd") or "").strip()
        cwd = self._bash_default_root() if raw_cwd in ("", ".") else self._resolve(raw_cwd)
        if not cwd.is_dir():
            raise NotADirectoryError(str(cwd))
        timeout = min(int(args.get("timeout_seconds", self.timeout)), self.timeout)
        return command, cwd, timeout

    def _resolve(self, raw: str, *, write: bool = False) -> Path:
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("paths must be relative and cannot contain '..'")
        resolved = (self.root / path).resolve()
        if self._touches_hidden(resolved):
            raise PermissionError(f"path is sealed and unavailable to this role: {raw}")
        roots = self.writable if write else self.visible
        if not self._under(resolved, roots):
            raise PermissionError(f"path is outside role boundary: {raw}")
        return resolved

    def execute(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "list_files":
                raw_path = str(args["path"]).strip().rstrip("/") or "."
                if raw_path in (".", "repo", "public/repo"):
                    return json.dumps({
                        "error": (
                            "broad repository listing is disabled. First read the evidence you are "
                            "allowed to see (e.g. public/problem_statement.md, "
                            "public/interface_contract.md, restricted/original_test.patch), then list "
                            "one targeted repo directory inferred from that evidence."
                        )
                    })
                path = self._resolve(raw_path)
                if path.is_file():
                    return str(path.relative_to(self.root))
                items = [str(item.relative_to(self.root)) for item in sorted(path.rglob("*")) if item.is_file()]
                visible = items[:500]
                suffix = "\n[truncated: use a narrower path]" if len(items) > len(visible) else ""
                return ("\n".join(visible) + suffix)[:20_000]
            if name == "read_file":
                path = self._resolve(str(args["path"]))
                data = path.read_text(encoding="utf-8", errors="replace")
                return data[:200_000]
            if name == "write_file":
                path = self._resolve(str(args["path"]), write=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(args["content"]), encoding="utf-8")
                return json.dumps({"written": str(path.relative_to(self.root)), "bytes": path.stat().st_size})
            if name == "run_bash":
                command, cwd, timeout = self.validate_bash(args)
                # Default cwd is the role's own first visible root, never the
                # workspace root: running at the root let `ls -R .` enumerate the
                # sealed directory's name even though reading into it was blocked.
                safe_env = {
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "LANG": os.environ.get("LANG", "C.UTF-8"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "HOME": str(cwd),
                }
                result = subprocess.run(
                    ["bash", "-lc", command], cwd=cwd, env=safe_env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False,
                )
                return json.dumps({"exit_code": result.returncode, "output": result.stdout[-50_000:]})
            raise KeyError(f"unknown tool: {name}")
        except Exception as exc:  # tool errors are evidence for the agent, not runtime crashes
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
