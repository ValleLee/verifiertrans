"""Shared helpers for the SWE-Pro → functional-verifier conversion pipeline.

Everything here is deterministic: no model calls, no container calls that depend
on model output.  These functions are the foundation the agent roles stand on,
so they are unit-tested in ``tests/test_core.py``.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any

# ``before_repo_set_cmd`` is a fixed four-command sequence in SWE-Bench Pro:
#
#     git reset --hard <base>
#     git clean -fd
#     git checkout <base>
#     git checkout <pr_commit> -- <test files>
#
# The last line restores the *post-fix* test files into the working tree, so it
# is what makes ``test_patch`` applyable later.  Building a "base" state as a
# plain checkout of ``base_commit`` is therefore wrong: the f2p tests could fail
# because the test file itself is stale rather than because the feature is
# missing, which would make every downstream base-fail verdict meaningless.
BASE_STATE_COMMANDS = (
    "git reset --hard {base_commit}",
    "git clean -fd",
    "git checkout {base_commit}",
)

#: Matches the three observed ``instance_id`` tail shapes:
#: ``-<sha40>``, ``-v<sha40>`` and ``-vnan``.
_INSTANCE_TAIL = re.compile(r"-(?:v(?P<version>[0-9a-f]{40})|vnan|(?P<sha>[0-9a-f]{40}))$")
_FIRST_SHA40 = re.compile(r"(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])")
_CHECKOUT_COMMIT = re.compile(r"git\s+checkout\s+(\S+)\s+--")


def safe_name(value: str) -> str:
    """Filesystem-safe form of an instance id."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def as_list(value: Any) -> list[str]:
    """Coerce a parquet list-ish field into a list of strings.

    SWE-Bench Pro stores ``fail_to_pass``/``pass_to_pass`` as JSON-array *text*,
    so a plain ``str`` round-trip is not enough.
    """
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    text = str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"unparseable list field: {text[:120]!r}") from exc
    if isinstance(parsed, str):
        # Some rows double-encode, e.g. a JSON string containing a JSON array.
        return as_list(parsed)
    if not isinstance(parsed, list):
        raise ValueError(f"expected list-like value, got {type(parsed).__name__}")
    return [str(item) for item in parsed]


def parse_instance_id(instance_id: str) -> dict[str, str | None]:
    """Extract the PR commit and optional version tag from an instance id.

    All three observed tail shapes carry a usable 40-hex PR commit.  Treating
    "the tail is not exactly 40 hex chars" as "missing commit" is wrong for the
    ``-v<sha>`` (368 rows) and ``-vnan`` (62 rows) families; ``vnan`` only means
    the version field is empty.
    """
    raw = str(instance_id)
    body = raw[len("instance_") :] if raw.startswith("instance_") else raw
    match = _FIRST_SHA40.search(body)
    if match is None:
        raise ValueError(f"no 40-hex commit found in instance_id: {raw!r}")
    commit = match.group(1)
    tail = body[match.end() :].lstrip("-")
    version: str | None = None
    tail_kind = "sha_only"
    if tail == "vnan":
        tail_kind = "vnan"
    elif re.fullmatch(r"v[0-9a-f]{40}", tail):
        version = tail[1:]
        tail_kind = "v_sha"
    elif tail:
        tail_kind = f"other:{tail[:32]}"
    return {"pr_commit": commit, "version_commit": version, "tail_kind": tail_kind}


def build_base_state_script(base_commit: str, before_repo_set_cmd: str) -> str:
    """Return the shell that reproduces the dataset's base working tree.

    The dataset's own command is authoritative and is what actually runs. The
    canonical reset/checkout is emitted first **only** when the dataset command is
    empty or does not already reset to ``base_commit`` — real rows all contain the
    full sequence, and prefixing it again would repeat the reset and restore the
    test files from the wrong commit before they are restored correctly.
    """
    dataset_cmd = "; ".join(part.strip() for part in str(before_repo_set_cmd or "").splitlines() if part.strip())
    if dataset_cmd and f"reset --hard {base_commit}" in dataset_cmd:
        return dataset_cmd
    prefix = "; ".join(command.format(base_commit=base_commit) for command in BASE_STATE_COMMANDS)
    return f"{prefix}; {dataset_cmd}" if dataset_cmd else prefix


def checkout_commit(before_repo_set_cmd: str) -> str | None:
    """The commit whose test files are restored into the base tree."""
    matches = _CHECKOUT_COMMIT.findall(str(before_repo_set_cmd or ""))
    return matches[0] if matches else None


def image_ref(dockerhub_tag: str) -> str:
    tag = str(dockerhub_tag)
    return tag if "/" in tag else f"jefzda/sweap-images:{tag}"


# --------------------------------------------------------------------------
# Interface contract extraction
# --------------------------------------------------------------------------
# ``interface`` is freeform text made of repeated blocks.  Two quirks of the real
# data have to be handled before anything else works:
#
# 1. the field is stored repr-quoted with *literal* ``\n`` sequences, so it must
#    be unescaped before line splitting (598 of 731 rows are affected by this);
# 2. field names vary across rows — ``Path``/``Pathfile``/``Location``/``File``
#    all mean "which file the reference solution touched", and ``Input``/
#    ``Inputs``, ``Output``/``Outputs`` are the same field spelled differently.
#
# ``Name``/input/output and declared errors are the contract a solver must
# honour.  Every location and prose field describes *how the reference solution
# was written* — ``Path:`` is literally the files the gold patch touched — so
# they are dropped before any agent sees the text.

CONTRACT_FIELDS = ("Type", "Name", "Input", "Output", "Raises", "Errors")
_LOCATION_FIELDS = {"Path", "Pathfile", "File", "Files", "Location", "Locations", "Module"}
_PROSE_FIELDS = {"Description", "Note", "Notes", "Example", "Examples", "Behavior", "Details"}
_DROPPED_FIELDS = _LOCATION_FIELDS | _PROSE_FIELDS

#: Canonical spelling for fields whose name varies between rows.
_FIELD_ALIASES = {
    "inputs": "Input",
    "input": "Input",
    "parameters": "Input",
    "outputs": "Output",
    "output": "Output",
    "returns": "Output",
    "return": "Output",
    "type": "Type",
    "name": "Name",
    "path": "Path",
    "pathfile": "Path",
    "file": "Path",
    "files": "Path",
    "location": "Path",
    "locations": "Path",
    "module": "Path",
    "description": "Description",
    "note": "Note",
    "notes": "Note",
    "example": "Example",
    "examples": "Example",
    "behavior": "Behavior",
    "details": "Details",
    "raises": "Raises",
    "errors": "Errors",
    "error": "Errors",
}

#: Every recognised field label, matched *anywhere* in the text.  Real rows pack
#: fields inline as often as they put them on separate lines:
#:
#:     Name: webfinger Type: Function Location: src/controllers/well-known.js
#:     name: `String` path: `internal/config/tracing.go` input: receiver `(e TracingBackend)`
#:
#: so a line-oriented parser is not enough — the field labels are what delimit
#: values, not newlines.  Matching anywhere also keeps a block title that happens
#: to contain a field word (``1) Controller: ... routes Location: ...``) from
#: being mistaken for a field, because the title is consumed as prose until the
#: first real label.
_ANY_FIELD = re.compile(
    r"(?P<key>"
    r"Type|Name|Symbol|Function|Method|Inputs?|Parameters|Outputs?|Returns?|"
    r"Raises|Errors?|Path|Pathfile|Files?|Locations?|Module|"
    r"Description|Notes?|Examples?|Behavior|Details"
    r")\s*:\s*",
    re.IGNORECASE,
)
#: Some rows bullet their fields (``- Name: `x` ``) and a few omit the colon
#: entirely (``- Signature `func F(...)` ``).  Bullets are stripped before field
#: scanning; colonless labels are handled by the aliases below.
_BULLET = re.compile(r"^\s*[-*•]\s+")
_COLONLESS_FIELD = re.compile(
    r"(?i)^(?P<key>Type|Name|Symbol|Signature|Inputs?|Parameters|Outputs?|Returns?|"
    r"Raises|Errors?|Path|Pathfile|Files?|Locations?|Module|Description|Notes?)\s+"
)
_NUMBERED_HEADING = re.compile(r"^\s*\d+\)\s*(?P<title>.+?)\s*$")


def unescape_field(raw: Any) -> str:
    """Turn a repr-quoted parquet string field into real text.

    The ``interface`` column arrives as a single line containing literal ``\\n``
    escapes.  ``unicode_escape`` would mangle non-ASCII (there are curly quotes
    in real rows), so only the known escape sequences are expanded.
    """
    text = str(raw or "")
    if "\\n" not in text and "\\t" not in text and not text.startswith('"'):
        return text
    if len(text) >= 2 and text[0] == text[-1] == '"':
        try:
            decoded = ast.literal_eval(text)
            if isinstance(decoded, str):
                text = decoded
        except (ValueError, SyntaxError):
            pass
    if "\\n" in text or "\\t" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return text


def split_interface_blocks(text: str) -> list[dict[str, str]]:
    """Split the interface field into ``{field: value}`` blocks.

    Fields are delimited by their labels rather than by newlines, because rows
    mix both layouts.  A block opens at ``Name``/``Symbol`` (or at a numbered
    heading such as ``1) Controller: WebFinger handler``); ``Type`` alone does
    not open one, since it usually precedes ``Name`` in the same block.
    """
    body = unescape_field(text)
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    pending_heading: str | None = None

    def flush() -> None:
        nonlocal current, pending_heading
        if current:
            if pending_heading and "Heading" not in current:
                current["Heading"] = pending_heading
            blocks.append(current)
        current = {}
        pending_heading = None

    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        stripped = _BULLET.sub("", stripped)
        if not stripped:
            continue
        heading = _NUMBERED_HEADING.match(stripped)
        if heading:
            flush()
            pending_heading = heading.group("title").strip()
            stripped = stripped[heading.end():].strip()
            if not stripped:
                continue

        matches = list(_ANY_FIELD.finditer(stripped))
        if not matches:
            # A colonless field (``Signature func F(...)``) — treat the label as
            # a field so its value is still parsed and scrubbed.
            colonless = _COLONLESS_FIELD.match(stripped)
            if colonless:
                key = colonless.group("key")
                value = stripped[colonless.end():].strip()
                canonical = _FIELD_ALIASES.get(key.lower(), key.title())
                if canonical in ("Name", "Symbol"):
                    if "Name" in current or current:
                        flush()
                    canonical = "Name"
                if canonical in current and canonical != "Name":
                    current[canonical] = f"{current[canonical]} {value}".strip()
                else:
                    current[canonical] = value
                continue
            # Prose that belongs to whatever block is open.
            if current:
                current["Description"] = f"{current.get('Description', '')} {stripped}".strip()
            continue

        # Text before the first label is either a block title or leading prose.
        lead = stripped[: matches[0].start()].strip(" -–:")
        if lead and not current:
            pending_heading = pending_heading or lead
        elif lead and current:
            current.setdefault("Description", "")
            current["Description"] = f"{current['Description']} {lead}".strip()

        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
            value = stripped[match.end(): end].strip().strip("`").strip()
            canonical = _FIELD_ALIASES.get(match.group("key").lower(), match.group("key").title())
            if canonical in ("Name", "Symbol") and ("Name" in current or current):
                flush()
            if canonical == "Symbol":
                canonical = "Name"
            if canonical in current and canonical != "Name":
                current[canonical] = f"{current[canonical]} {value}".strip()
            elif canonical in current:
                current[canonical] = value
            else:
                current[canonical] = value
    flush()
    return [block for block in blocks if block]


#: Rows whose ``interface`` field carries no interface content at all.  507 of
#: the 731 rows say something like "No new interfaces are introduced", which is
#: a real answer (the task added no public API) and not a parse failure.
_NO_INTERFACE = re.compile(
    r"^\s*(no\s+(new\s+)?(public\s+)?(interface|interfaces|api|apis|symbol|symbols)\b"
    r"|none\b|n/?a\b|not\s+applicable\b)",
    re.IGNORECASE,
)


def has_interface_content(text: str) -> bool:
    """False when the field states there are no new interfaces (or is empty)."""
    stripped = unescape_field(text).strip().strip('"').strip()
    if not stripped:
        return False
    return _NO_INTERFACE.match(stripped) is None


#: Labels whose *value* is safe to show a solver: API shape only.  Everything
#: else is either a location (gold-patch pointer) or prose (a description of how
#: the reference implemented it).  A whitelist is used rather than a blacklist
#: because the set of location spellings in the real data is open-ended
#: (``Path``/``Pathfile``/``File``/``Location``/``Package``/``Module``/``Directory``
#: all occur, in several cases on one line).
_KEEP_LABELS = ("Kind", "Input", "Output", "Raises", "Errors")

#: Prose that can start mid-value when a label is packed inline after a sentence
#: (``... HTTP 404 on cases Description: Handles GET /.well-known/webfinger``).
#: Cut from the label onward, then from the next sentence start, so an English
#: description never ends up inside ``Output:``.
_PROSE_INLINE = re.compile(
    r"(?i)\b(?:Description|Note|Notes|Behavior|Details|Purpose|Semantics)\s*:\s*"
)
#: A sentence boundary inside a scraped value, used as a final cut for freeform
#: rows where prose follows the typed part without any label.
_SENTENCE_CUT = re.compile(r"(?<=[a-z\)\]])\s+[A-Z][a-z]+(?:s)?\s+[a-z]")

#: A filesystem path token: two or more directory segments ending in a file or a
#: source extension, e.g. ``internal/config/tracing.go`` or ``src/controllers/``.
#: Deliberately strict — an earlier looser pattern matched type expressions like
#: ``Promise<(string | null)[]>`` (spaces and ``|`` read as path separators) and
#: silently deleted valid contract values.  Path segments must therefore be
#: separator-free identifiers, and the tail must look like a file name.
_PATH_SEGMENT = r"[\w.@-]+"
_BARE_PATH = re.compile(
    rf"(?<![\w./@-]){_PATH_SEGMENT}/(?:{_PATH_SEGMENT}/)+{_PATH_SEGMENT}"
    rf"(?:\.(?:py|js|ts|tsx|go|rs|rb|java|kt|c|cc|cpp|h|hpp|json|ya?ml|toml|md|txt|cfg|ini))?"
    rf"(?![\w/@-])"
)


def _clean_value(value: str, *, freeform: bool) -> tuple[str, int]:
    """Strip paths and trailing prose from one field value."""
    removed = 0
    cleaned = value
    prose = _PROSE_INLINE.search(cleaned)
    if prose:
        cleaned = cleaned[: prose.start()]
        removed += 1
    cleaned, hits = _BARE_PATH.subn("", cleaned)
    removed += hits
    if freeform:
        cut = _SENTENCE_CUT.search(cleaned)
        if cut and cut.start() > 12:
            cleaned = cleaned[: cut.start()]
            removed += 1
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ,;–-"), removed


def scrub_contract(text: str, *, freeform: bool = False) -> tuple[str, int]:
    """Reduce an assembled contract to whitelisted shape-only fields.

    The scrub is the safety net behind the parser: even if block splitting
    mis-segments a row, nothing reaches an agent except a ``###`` symbol heading
    and the whitelisted field lines beneath it.  A heading that is itself a file
    path is dropped.  ``residual_scrubbed`` counts what this caught, which is the
    signal that the parser (not the scrub) needs attention.
    """
    removed = 0
    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("###"):
            title = stripped[3:].strip()
            if not title or _BARE_PATH.search(title) or "/" in title:
                removed += 1
                continue
            lines_out.append(f"### {title}")
            continue

        body = stripped.lstrip("-* ").strip()
        if ":" in body:
            label, _, value = body.partition(":")
            label = _FIELD_ALIASES.get(label.strip().lower(), label.strip())
            if label in _KEEP_LABELS:
                cleaned, hits = _clean_value(value, freeform=freeform)
                removed += hits
                if cleaned:
                    lines_out.append(f"- {label}: {cleaned}")
                continue
        # Anything not whitelisted (locations, prose, bare paths) is dropped.
        removed += 1
    cleaned = "\n".join(lines_out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned + "\n", removed


def extract_contract(interface_text: str, problem_statement: str = "") -> tuple[str, dict[str, Any]]:
    """Return ``(contract_markdown, audit)`` for the solver-visible contract subset.

    Only declared API shape survives: symbol name, signature-ish input, output
    type and declared error type.  Implementation locations and prose
    descriptions are dropped, because in SWE-Bench Pro they are derived from the
    reference patch and would leak the answer to the spec-writing role.

    Three outcomes are distinguished, and the choice is recorded in the audit so
    the report can tell them apart:

    ``structured``
        Parsed into named API blocks; the normal case (133 rows).
    ``no_new_interfaces``
        The field states the task introduced no public API, so the problem
        statement *is* the contract.  Not an error (507 rows).
    ``freeform_field_scrape``
        Prose with inline fields that the block parser cannot segment; fields
        are scraped individually.  Recorded because it is lower-fidelity.
    """
    text = unescape_field(interface_text)
    blocks = split_interface_blocks(text)
    kept: list[str] = []
    dropped_fields: set[str] = set()
    for block in blocks:
        name = block.get("Name") or block.get("Heading") or block.get("Symbol") or ""
        if not name:
            continue
        lines = [f"### {name}"]
        kind = block.get("Type")
        if kind:
            lines.append(f"- Kind: {kind}")
        for field in CONTRACT_FIELDS:
            if field in ("Name", "Type"):
                continue
            if block.get(field):
                lines.append(f"- {field}: {block[field]}")
        kept.append("\n".join(lines))
        dropped_fields.update(key for key in block if key in _DROPPED_FIELDS)

    if kept:
        contract, scrubbed = scrub_contract("\n\n".join(kept) + "\n")
        # A contract that survives parsing but carries almost no API shape is
        # worse than the problem statement: it looks authoritative while telling
        # the downstream model sessions nothing useful. Treat it as unparsed.
        shape_fields = [line for line in contract.splitlines() if line.startswith("- ")]
        if len(shape_fields) < 2:
            return _fallback(problem_statement, blocks, text, "insufficient_shape",
                             kept=len(kept), dropped=sorted(dropped_fields), scrubbed=scrubbed)
        audit = {
            "mode": "structured",
            "blocks_total": len(blocks),
            "blocks_kept": len(kept),
            "shape_fields": len(shape_fields),
            "fields_dropped": sorted(dropped_fields),
            "residual_scrubbed": scrubbed,
        }
        return contract, audit

    if not has_interface_content(text):
        return str(problem_statement or "").strip() + "\n", {
            "mode": "no_new_interfaces",
            "blocks_total": len(blocks),
            "blocks_kept": 0,
            "shape_fields": 0,
            "fields_dropped": [],
            "residual_scrubbed": 0,
            "raw_interface": text.strip()[:200],
        }

    scraped = _scrape_inline_fields(text)
    if scraped and len([line for line in scraped[0].splitlines() if line.startswith("- ")]) >= 2:
        contract, scrubbed = scrub_contract(scraped[0], freeform=True)
        shape_fields = [line for line in contract.splitlines() if line.startswith("- ")]
        return contract, {
            "mode": "freeform_field_scrape",
            "blocks_total": len(blocks),
            "blocks_kept": 0,
            "shape_fields": len(shape_fields),
            "fields_dropped": sorted(scraped[1]),
            "residual_scrubbed": scrubbed,
            "raw_interface": text.strip()[:200],
        }

    return _fallback(problem_statement, blocks, text, "unparseable_prose")


def _fallback(
    problem_statement: str, blocks: list[dict[str, str]], text: str, reason: str,
    *, kept: int = 0, dropped: list[str] | None = None, scrubbed: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Contract-is-the-problem-statement outcome, with the reason recorded.

    These are the rows where the ``interface`` field describes the change in
    prose rather than declaring an API (or is a sentence about the gold patch
    itself).  The problem statement becomes the contract, and the row is counted
    in the report so the degraded path is visible rather than silent.
    """
    return str(problem_statement or "").strip() + "\n", {
        "mode": "fallback_problem_statement",
        "reason": reason,
        "blocks_total": len(blocks),
        "blocks_kept": kept,
        "shape_fields": 0,
        "fields_dropped": dropped or [],
        "residual_scrubbed": scrubbed,
        "raw_interface": text.strip()[:200],
    }


#: Ordered contract fields, used both for block rendering and inline scraping.
_INLINE_FIELD = re.compile(
    r"\b(?P<key>Function|Method|Type|Name|Input|Inputs|Output|Outputs|Returns|Raises|Errors)\s*:",
    re.IGNORECASE,
)


def _scrape_inline_fields(text: str) -> tuple[str, set[str]]:
    """Best-effort field scrape for prose interfaces the block parser rejects."""
    matches = list(_INLINE_FIELD.finditer(text))
    if not matches:
        return "", set()
    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        canonical = _FIELD_ALIASES.get(match.group("key").lower(), match.group("key"))
        chunks.append((canonical, value))
    lines = ["### Declared interface (scraped from prose)"]
    dropped: set[str] = set()
    for key, value in chunks:
        if key in _DROPPED_FIELDS:
            dropped.add(key)
            continue
        if key == "Name":
            continue
        if value:
            lines.append(f"- {key}: {' '.join(value.split())[:600]}")
    return "\n".join(lines) + "\n", dropped


# --------------------------------------------------------------------------
# Test-id normalisation
# --------------------------------------------------------------------------
# Python/Go rows use pytest-style node ids (``path::Class::method``); JS/TS rows
# use a different convention, e.g.
#
#     test/database.js | Test database test/database/keys.js::Key methods ...
#
# where the part before ``|`` is the file the runner was pointed at and the part
# after ``|`` is ``<suite label> <file>::<case name>``.  The file appearing twice
# is redundant, so the normalised form keeps the leading file plus the case name
# only — otherwise the same logical test compares unequal between base and gold
# runs that report it in different shapes.

_JS_NODE = re.compile(r"^(?P<file>[^|]+?)\s*\|\s*(?P<rest>.*)$")
_JS_CASE = re.compile(r"::\s*(?P<case>.+)$")

# Dataset selectors are sometimes copied from the container command that
# produced them.  ``/app`` and ``/workspace`` are execution roots, not paths
# inside the repository mounted by VerifierTrans.  Keep this normalization
# generic: it applies to every language and does not name a repository or test.
_LOGICAL_REPO_ROOTS = (
    "/workspace/app/",
    "/workspace/",
    "/app/",
    "workspace/app/",
    "workspace/",
    "app/",
)
_TEST_EXTENSION_ALIASES = {
    # Dataset selectors sometimes preserve the generated runner's JavaScript
    # spelling while the checked-out TypeScript repository stores the same
    # test under the corresponding .ts/.tsx path (and vice versa).  Exact
    # paths are still tried first; these are only same-stem fallbacks.
    ".ts": (".tsx", ".js"),
    ".tsx": (".ts", ".jsx"),
    ".js": (".jsx", ".ts"),
    ".jsx": (".js", ".tsx"),
}


@lru_cache(maxsize=32)
def _repo_file_basename_index(repo_text: str) -> dict[str, tuple[str, ...]]:
    """Build one deterministic basename index for a prepared repository."""
    repo = Path(repo_text)
    index: dict[str, list[str]] = {}
    for candidate in repo.rglob("*"):
        if candidate.is_file():
            relative = candidate.relative_to(repo).as_posix()
            index.setdefault(candidate.name, []).append(relative)
    return {name: tuple(sorted(paths)) for name, paths in index.items()}


def normalize_repo_path(value: str) -> str:
    """Convert a dataset/container test path to a repository-relative path."""
    text = str(value).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    for prefix in _LOGICAL_REPO_ROOTS:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def resolve_repo_test_path(repo: Path, value: str) -> str:
    """Resolve a normalized selector path, including JS/TS extension aliases.

    A few dataset rows record the extension used by a generated test command
    rather than the checked-out source file.  Exact paths remain authoritative;
    the alias fallback is deterministic and limited to the standard JS/TS
    source extensions. If generated directory groupings differ, a unique
    same-stem basename match is accepted; ambiguous matches are rejected.
    """
    normalized = normalize_repo_path(value)
    candidates = [normalized]
    path = Path(normalized)

    # Some generated SWE-Pro selectors add an extra ``tests`` component below
    # the repository's conventional ``test/`` root.  Treat it as a logical
    # test-root spelling, not as a repository-specific exception.
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "test" and parts[1] == "tests":
        candidates.append(Path("test", *parts[2:]).as_posix())

    # Apply extension aliases to every logical path spelling.  Exact paths
    # remain first, so an actual .js file wins over a same-stem .ts fallback.
    for candidate_path in tuple(candidates):
        suffixes = _TEST_EXTENSION_ALIASES.get(Path(candidate_path).suffix.lower(), ())
        candidates.extend(
            Path(candidate_path).with_suffix(suffix).as_posix()
            for suffix in suffixes
        )
    for candidate in candidates:
        if (repo / candidate).is_file():
            return candidate

    # Some generated selectors contain historical grouping directories that
    # were flattened in the checkout (for example ``.../utils/Foo.js`` versus
    # ``.../Foo.ts``). Fall back only when the same-stem basename is unique in
    # the repository; ambiguous names remain unresolved and are reported by
    # Prepare instead of being guessed.
    suffixes = (path.suffix, *_TEST_EXTENSION_ALIASES.get(path.suffix.lower(), ()))
    names = {path.with_suffix(suffix).name for suffix in suffixes}
    basename_index = _repo_file_basename_index(str(repo))
    matches = sorted({match for name in names for match in basename_index.get(name, ())})
    if len(matches) == 1:
        return matches[0]
    return normalized


def normalize_node_id(node_id: str, language: str = "") -> str:
    """Reduce a runner-reported test id to a stable ``(file, node)`` form."""
    text = str(node_id).strip()
    if not text:
        return ""
    if language.lower() in {"js", "ts", "javascript", "typescript"} or "|" in text:
        match = _JS_NODE.match(text)
        if match:
            case = _JS_CASE.search(match.group("rest"))
            file = normalize_repo_path(match.group("file"))
            if case:
                return f"{file}::{case.group('case').strip()}"
            return f"{file}::{match.group('rest').strip()}"
    if "::" in text:
        file, rest = text.split("::", 1)
        return f"{normalize_repo_path(file)}::{rest}"
    return normalize_repo_path(text)


def node_id_file(node_id: str) -> str:
    """The file portion of a node id (before the first ``::``)."""
    return normalize_node_id(node_id).split("::", 1)[0]


# --------------------------------------------------------------------------
# Result-diff classification
# --------------------------------------------------------------------------
def classify_results(
    base_results: dict[str, bool],
    gold_results: dict[str, bool],
    inherited_p2p: list[str],
) -> dict[str, Any]:
    """Split observed test outcomes into f2p / p2p / anomalies.

    ``p2p`` is inherited from SWE-Bench Pro rather than recomputed; the only
    check applied to it here is liveness against the freshly observed run.
    ``f2p`` is not copied from the source ``fail_to_pass`` either: it is the set
    of tests that actually fail on base and pass on gold under the *converted*
    verifier, which is a by-product of the replay we already run.
    """
    f2p = sorted(node for node, passed in gold_results.items() if passed and not base_results.get(node, False))
    anomalies = {
        "gold_failed": sorted(node for node, passed in gold_results.items() if not passed),
        "base_passed_new": sorted(node for node, passed in base_results.items() if passed and node not in set(inherited_p2p)),
    }
    inherited_present = [node for node in inherited_p2p if node in gold_results]
    inherited_missing = sorted(node for node in inherited_p2p if node not in gold_results)
    inherited_regressed = sorted(node for node in inherited_present if not gold_results[node])
    return {
        "f2p": f2p,
        "p2p_inherited": sorted(inherited_p2p),
        "p2p_present": sorted(inherited_present),
        "p2p_missing": inherited_missing,
        "p2p_regressed": inherited_regressed,
        "anomalies": anomalies,
    }
