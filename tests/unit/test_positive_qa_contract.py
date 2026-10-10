from verifier_trans.pipeline.qa import (
    POSITIVE_CONTRACT_VERSION,
    positive_candidate_contract,
    positive_execution_contract,
    validated_positive_contract,
)


def result(accepted: bool, runnable: bool = True, failure_class: str = "NONE") -> dict:
    return {"accepted": accepted, "runnable": runnable, "failure_class": failure_class}


def test_historical_pass_is_audit_only() -> None:
    contract = positive_execution_contract(result(True), result(True), result(True))
    assert contract["accepted"] is True
    assert contract["historical_f2p_pass"] is True


def test_historical_fail_is_also_audit_only() -> None:
    contract = positive_execution_contract(result(True), result(True), result(False))
    assert contract["accepted"] is True
    assert contract["historical_f2p_pass"] is False
    assert contract["legacy_f2p_separation"] is True
    assert contract["contract_version"] == POSITIVE_CONTRACT_VERSION == 5


def test_historical_infrastructure_does_not_prove_separation() -> None:
    contract = positive_execution_contract(result(True), result(True), result(False, False, "INFRASTRUCTURE"))
    assert contract["accepted"] is True
    assert contract["historical_f2p_infrastructure"] is True


def test_current_f2p_or_p2p_failure_rejects_positive() -> None:
    assert positive_execution_contract(result(True), result(False), result(True))["accepted"] is False
    assert positive_execution_contract(result(False), result(True), result(True))["accepted"] is False


def test_runnable_current_f2p_failure_still_reaches_semantic_adjudication() -> None:
    contract = positive_candidate_contract(
        result(True), result(False), result(False),
        {"exact_gold_reproduction": False},
    )
    assert contract["status"] == "candidate_positive"
    assert contract["eligible_for_adjudication"] is True
    assert contract["current_f2p_failure_is_semantic"] is True


def test_validated_positive_failure_is_a_hard_false_negative() -> None:
    contract = validated_positive_contract(
        True, result(True), result(False), result(False)
    )
    assert contract["status"] == "validated_positive"
    assert contract["hard_false_negative"] is True
    assert contract["accepted"] is False


def test_invalid_candidate_failure_is_not_a_verifier_false_negative() -> None:
    contract = validated_positive_contract(
        False, result(True), result(False), result(False)
    )
    assert contract["hard_false_negative"] is False
    assert contract["status"] == "candidate_positive"


def test_infrastructure_failure_is_not_a_verifier_false_negative() -> None:
    contract = validated_positive_contract(
        True, result(True), result(False, failure_class="INFRASTRUCTURE"), result(False)
    )
    assert contract["hard_false_negative"] is False
