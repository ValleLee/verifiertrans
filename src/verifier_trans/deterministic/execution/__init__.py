"""Deterministic repository execution adapters used by replay and QA.

The Converter owns *what* is tested.  This package owns the small amount of
runtime plumbing needed to execute that artifact in a task image: language
runner, selector runner, container paths and service bootstrap.
"""

from .base import (
    EXECUTION_CONTRACT_VERSION,
    ExecutionPlan,
    PackageExecutionPlan,
    execution_spec,
    execution_plan,
    package_execution_plan,
    parse_result_marker,
    standard_role_mounts,
    contract_environment_args,
)
from .discovery import ExecutionSpec, discover_execution_spec, execution_spec_hash
from .services import service_bootstrap_script

__all__ = [
    "EXECUTION_CONTRACT_VERSION",
    "ExecutionPlan",
    "PackageExecutionPlan",
    "ExecutionSpec",
    "discover_execution_spec",
    "execution_spec_hash",
    "execution_spec",
    "execution_plan",
    "package_execution_plan",
    "parse_result_marker",
    "standard_role_mounts",
    "contract_environment_args",
    "service_bootstrap_script",
]
