"""Central filesystem contract for source files and run artifacts."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "experiment.yaml"
DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "runs"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_instance_id(instance_id: str) -> str:
    value = str(instance_id).strip()
    if not value or value in {".", ".."}:
        raise ValueError("instance_id must be non-empty")
    if "/" in value or "\\" in value or Path(value).name != value:
        raise ValueError(f"instance_id contains a path separator: {value!r}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _relative_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve(strict=False) == target.resolve(strict=False):
            return
        link.unlink()
    elif link.exists():
        raise FileExistsError(f"compatibility path already exists: {link}")
    link.symlink_to(os.path.relpath(target, link.parent))


@dataclass(frozen=True)
class AttemptLayout:
    """One immutable-from-Prepare conversion attempt."""

    root: Path

    @property
    def runtime(self) -> Path:
        """Hidden compatibility view consumed by deterministic legacy interfaces."""
        return self.root / ".compat"

    @property
    def run_root(self) -> Path:
        """Instance root for the current layout, or the attempt for legacy fixtures."""
        if self.root.parent.name == "attempts" and self.root.parent.parent.name == "intermediate":
            return self.root.parents[2]
        return self.root

    @property
    def source(self) -> Path:
        canonical = self.run_root / "source"
        return canonical if canonical.exists() else self.root / "source"

    @property
    def prepare(self) -> Path:
        return self.root / "prepare"

    @property
    def converter(self) -> Path:
        return self.root / "converter"

    @property
    def validation(self) -> Path:
        return self.root / "validation"

    @property
    def qa(self) -> Path:
        return self.root / "qa"

    @property
    def packaging(self) -> Path:
        return self.root / "packaging"

    @property
    def control(self) -> Path:
        return self.root / "control"

    def create(self) -> "AttemptLayout":
        # New attempts share one instance-level immutable source boundary.
        # Existing attempt-centric layouts are left untouched and remain
        # readable through the fallback above.
        canonical_source = self.run_root / "source"
        if self.run_root != self.root:
            for directory in ("public", "restricted", "sealed", "reference"):
                (canonical_source / directory).mkdir(parents=True, exist_ok=True)
            legacy_source = self.root / "source"
            if not legacy_source.exists() and not legacy_source.is_symlink():
                _relative_symlink(legacy_source, canonical_source)
        directories = (
            self.source / "public",
            self.source / "restricted",
            self.source / "sealed",
            self.source / "reference",
            self.prepare / "logs",
            self.converter / "current",
            self.converter / "revisions",
            self.converter / "staging",
            self.converter / "trajectories",
            self.converter / "live",
            self.validation / "sanity",
            self.validation / "semantic",
            self.validation / "hard_replay",
            self.validation / "evidence_replay",
            self.qa / "positive",
            self.qa / "negative",
            self.qa / "candidates",
            self.packaging / "candidate_task",
            self.packaging / "logs",
            self.control,
            self.runtime / "artifacts",
            self.runtime / "run",
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        directory_links = {
            self.runtime / "public": self.source / "public",
            self.runtime / "restricted": self.source / "restricted",
            self.runtime / "sealed": self.source / "sealed",
            self.runtime / "reference": self.source / "reference",
            self.runtime / "verifier": self.converter / "current",
            self.runtime / "artifacts" / "verifier": self.converter / "revisions",
            self.runtime / "artifacts" / "staging": self.converter / "staging",
            self.runtime / "artifacts" / "trajectories": self.converter / "trajectories",
            self.runtime / "artifacts" / "live": self.converter / "live",
            self.runtime / "artifacts" / "validation": self.validation / "sanity",
            self.runtime / "artifacts" / "semantic_reviews": self.validation / "semantic",
            self.runtime / "artifacts" / "core_gate": self.validation / "hard_replay",
            self.runtime / "artifacts" / "positives": self.qa / "positive",
            self.runtime / "artifacts" / "mutations": self.qa / "negative",
            self.runtime / "run" / "logs": self.prepare / "logs",
            self.runtime / "run" / "validator": self.qa / "candidates",
        }
        for link, target in directory_links.items():
            _relative_symlink(link, target)

        file_links = {
            self.runtime / "state.json": self.control / "state.json",
            self.runtime / "events.jsonl": self.control / "events.jsonl",
            self.runtime / "evidence.json": self.qa / "evidence.json",
            self.runtime / "artifacts" / "package.json": self.packaging / "package_report.json",
            self.runtime / "run" / "metadata.json": self.prepare / "metadata.json",
            self.runtime / "run" / "source_row.json": self.prepare / "source_row.json",
            self.runtime / "run" / "source_preflight.json": self.prepare / "source_preflight.json",
            self.runtime / "run" / "environment_preflight.json": self.prepare / "environment_preflight.json",
            self.runtime / "run" / "check.json": self.validation / "hard_replay" / "latest_check.json",
            self.runtime / "run" / "final.json": self.control / "final.json",
            self.runtime / "run" / "report.json": self.control / "report.json",
            self.runtime / "run" / "converter_session.lock": self.control / "converter_session.lock",
        }
        for link, target in file_links.items():
            _relative_symlink(link, target)
        if self.run_root != self.root:
            _write_json(self.run_root / "layout_manifest.json", {
                "schema_version": "1.0",
                "run_root": str(self.run_root),
                "attempt_root": str(self.root),
                "source_root": str(self.source),
                "derived_root": str(self.root),
                "final_task": str(self.run_root / "final_task"),
                "compatibility_view": str(self.runtime),
            })
        return self


@dataclass(frozen=True)
class RunLayout:
    root: Path
    instance_id: str

    @classmethod
    def for_instance(cls, runs_root: Path, instance_id: str) -> "RunLayout":
        return cls(Path(runs_root).resolve() / validate_instance_id(instance_id), instance_id)

    @property
    def final_task(self) -> Path:
        return self.root / "final_task"

    @property
    def source(self) -> Path:
        return self.root / "source"

    @property
    def review(self) -> Path:
        return self.root / "review"

    @property
    def intermediate(self) -> Path:
        return self.root / "intermediate"

    @property
    def attempts(self) -> Path:
        return self.intermediate / "attempts"

    @property
    def latest_pointer(self) -> Path:
        return self.intermediate / "latest_attempt.json"

    def allocate_attempt(self) -> AttemptLayout:
        for directory in ("public", "restricted", "sealed", "reference"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
        self.review.mkdir(parents=True, exist_ok=True)
        self.attempts.mkdir(parents=True, exist_ok=True)
        numbers = [
            int(path.name.removeprefix("attempt_"))
            for path in self.attempts.glob("attempt_[0-9][0-9][0-9]")
        ]
        number = max(numbers, default=0) + 1
        attempt = AttemptLayout(self.attempts / f"attempt_{number:03d}").create()
        _write_json(
            self.latest_pointer,
            {
                "schema_version": "1.0",
                "instance_id": self.instance_id,
                "attempt": attempt.root.name,
                "path": str(attempt.root.relative_to(self.root)),
                "created_at_utc": utc_now(),
            },
        )
        return attempt

    def latest_attempt(self) -> AttemptLayout:
        if not self.latest_pointer.is_file():
            raise FileNotFoundError(f"no prepared attempt: {self.latest_pointer}")
        value = json.loads(self.latest_pointer.read_text(encoding="utf-8"))
        attempt = AttemptLayout(self.root / str(value["path"]))
        if not attempt.root.is_dir():
            raise FileNotFoundError(f"latest attempt is missing: {attempt.root}")
        return attempt.create()


def attempt_from_path(path: Path) -> AttemptLayout:
    candidate = Path(path).resolve()
    if candidate.name == ".compat":
        return AttemptLayout(candidate.parent).create()
    if (candidate / ".compat").is_dir():
        return AttemptLayout(candidate).create()
    raise ValueError(f"not a VerifierTrans attempt directory: {candidate}")
