from pathlib import Path


def test_successful_sanity_clears_previous_repair_packet() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    sanity_pass = source.index('if sanity.get("status") != "PASS":')
    semantic_start = source.index("semantic = (", sanity_pass)
    segment = source[sanity_pass:semantic_start]
    assert "packet = None" in segment


def test_semantic_judge_receives_source_and_resolved_f2p_ids() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert '"fail_to_pass_resolved"' in source
    assert "resolved_test_selectors.json" in source


def test_candidate_payload_can_survive_missing_submission_sentinel() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "RECOVERED_EXISTING_CANDIDATE_PAYLOAD" in source
    assert "did not emit the explicit submission signal" in source
    assert "output.resolve()" in source
    assert "uv_os_get_passwd" in source


def test_stale_positive_evidence_cannot_count_before_revalidation() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert '"positives": [' in source
    assert 'item.get("contract_version") == POSITIVE_CONTRACT_VERSION' in source


def test_controller_lease_rejects_concurrent_resume(tmp_path) -> None:
    import pytest

    from verifier_trans.pipeline.orchestrator import controller_session_lock

    with controller_session_lock(tmp_path):
        with pytest.raises(RuntimeError, match="another controller session"):
            with controller_session_lock(tmp_path):
                pass


def test_keyboard_interrupt_records_interrupted_state() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert 'append_event(workspace, "INTERRUPTED", "controller"' in source


def test_explicit_repair_packet_starts_a_new_converter_revision() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert '"--repair-packet"' in source
    assert 'loaded_packet = json.loads(packet_path.read_text' in source
    assert '"REPAIR_REQUESTED"' in source
    assert "args.resume = False" in source


def test_artifact_schema_repair_packet_explains_typed_manifest_files(tmp_path) -> None:
    from verifier_trans.pipeline.orchestrator import repair_packet

    packet = repair_packet(
        tmp_path,
        {"errors": ["manifest_test_files_0_not_object", "missing_functional_verifier_source"]},
        {},
        "verifier artifact violates the deterministic execution contract",
    )
    instruction = packet["instruction"]
    assert "JSON list of objects" in instruction
    assert '"source"' in instruction and '"target"' in instruction
    assert "functional_artifact" in instruction


def test_non_retryable_model_endpoint_errors_are_not_converter_repairs() -> None:
    from verifier_trans.pipeline.orchestrator import non_retryable_model_endpoint_error

    assert non_retryable_model_endpoint_error(
        RuntimeError("model API returned HTTP 402: Insufficient Balance")
    )
    assert non_retryable_model_endpoint_error(
        RuntimeError("model API returned HTTP 401: invalid API key")
    )
    assert not non_retryable_model_endpoint_error(
        RuntimeError("model API returned HTTP 429: rate limited")
    )
    assert not non_retryable_model_endpoint_error(RuntimeError("tool step limit"))


def test_infrastructure_failure_is_not_reported_as_manual_review() -> None:
    from verifier_trans.pipeline.orchestrator import automatic_terminal_state

    assert automatic_terminal_state({"accepted": False, "failure_domain": "infrastructure"}) == "INFRASTRUCTURE"
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(encoding="utf-8")
    assert '"status": "VERIFIED" if accepted else terminal_state' in source


def test_automatic_terminal_states_have_no_implicit_review_queue() -> None:
    from verifier_trans.pipeline.orchestrator import automatic_terminal_state

    assert automatic_terminal_state({"accepted": True}) == "FINAL_VALIDATED"
    assert automatic_terminal_state({"accepted": False, "failure_domain": "infrastructure"}) == "INFRASTRUCTURE"
    assert automatic_terminal_state({"accepted": False, "failure_domain": "package_smoke"}) == "PACKAGE"
    assert automatic_terminal_state({"accepted": False, "failure_domain": "verifier"}) == "FAILED"


def test_qa_model_endpoint_failures_stop_attempt_loops() -> None:
    source = Path("src/verifier_trans/pipeline/orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert 'non-retryable model endpoint failure during positive QA' in source
    assert 'non-retryable model endpoint failure during negative QA' in source
    assert 'if qa_failure:\n            final = qa_failure\n            break' in source
