"""Command-line entry point for VerifierTrans."""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        from .batch import main as batch_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return batch_main()
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        from .deterministic.reporting.report import main as report_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        return report_main()
    from .pipeline.orchestrator import main as controller_main
    return controller_main()


__all__ = ["main"]
