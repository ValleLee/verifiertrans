"""Deterministic optional service bootstrap for repository replay."""

from __future__ import annotations


def redis_bootstrap_script() -> str:
    """Return a bounded shell snippet for images that ship local Redis.

    The image remains authoritative: this only starts Redis when both commands
    already exist and the default local instance is not ready.
    """

    return """if command -v redis-cli >/dev/null 2>&1 && command -v redis-server >/dev/null 2>&1; then
  redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes >/dev/null 2>&1
  for _ in $(seq 1 30); do
    redis-cli ping >/dev/null 2>&1 && break
    sleep 0.1
  done
fi"""


def service_bootstrap_script(spec) -> str:
    """Render only services frozen in the Prepare execution contract."""
    services = tuple(getattr(spec, "services", ()) or ())
    unknown = sorted(set(services) - {"redis"})
    if unknown:
        raise ValueError("unsupported execution services: " + ",".join(unknown))
    return redis_bootstrap_script() if "redis" in services else ":"
