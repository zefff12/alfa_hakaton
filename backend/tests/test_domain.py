"""Модульные тесты доменной логики: калькулятор, скоринг, решение, машина состояний."""
import pytest

from app.domain import calculator, readiness
from app.domain.advisor import NeedProfile, recommend
from app.domain.decision import decide
from app.domain.products import PRODUCTS
from app.domain.scoring import ScoringInput, score
from app.domain.state_machine import Actor, Status, TransitionError, can_transition, ensure_transition


def good_input(**kw) -> ScoringInput:
    base = dict(business_age_months=60, monthly_revenue=4_500_000, monthly_expenses=3_600_000,
                existing_monthly_payments=180_000, new_monthly_payment=150_000, requested_amount=3_000_000,
                annual_revenue_reported=54_000_000, credit_history_months=52, industry="food")
    base.update(kw)
    return ScoringInput(**base)


def test_annuity_payment():
    pay = calculator.monthly_payment(1_000_000, 12, 12)
    assert round(pay) == 88_849
    assert calculator.max_amount_for_payment(pay, 12, 12) == pytest.approx(1_000_000, rel=1e-6)


def test_schedule_repays_principal():
    rows = calculator.schedule(500_000, 20, 10)
    assert len(rows) == 10
    assert rows[-1]["balance"] == 0
    assert sum(r["principal"] for r in rows) == pytest.approx(500_000, abs=1)


def test_good_borrower_scores_high():
    res = score(good_input())
    assert res.risk_class in ("A", "B")
    assert all(f.code for f in res.factors)


def test_delinquency_and_debt_burden_lower_score():
    good = score(good_input()).score
    bad = score(good_input(max_delinquency_days_12m=45, existing_monthly_payments=600_000)).score
    assert bad < good - 150


def test_decision_approves_good_borrower():
    inp = good_input()
    d = decide(PRODUCTS["WORKING"], inp, score(inp), term=24, purpose="working_capital")
    assert d.outcome == "APPROVED"
    assert d.offer["options"][0]["amount"] == 3_000_000


def test_same_score_different_products_give_different_decisions():
    """Скоринг ≠ решение: при той же оценке риска продукты дают разный результат."""
    inp = good_input(business_age_months=8, annual_revenue_reported=None)
    res = score(inp)
    working = decide(PRODUCTS["WORKING"], inp, res, term=24, purpose="working_capital")
    express = decide(PRODUCTS["EXPRESS"], inp, res, term=24, purpose="working_capital")
    assert working.outcome == "COUNTER_OFFER"  # по сроку работы не проходит → альтернативный продукт
    assert working.offer["product_code"] != "WORKING"
    assert express.outcome != "COUNTER_OFFER" or express.offer["product_code"] == "EXPRESS"


def test_counter_offer_when_amount_exceeds_capacity():
    inp = good_input(monthly_revenue=800_000, monthly_expenses=600_000, existing_monthly_payments=15_000,
                     annual_revenue_reported=9_600_000, requested_amount=3_000_000, business_age_months=26,
                     industry="retail", credit_history_months=14)
    d = decide(PRODUCTS["EXPRESS"], inp, score(inp), term=12, purpose="working_capital")
    assert d.outcome == "COUNTER_OFFER"
    assert all(o["monthly_payment"] <= 0.5 * 200_000 for o in d.offer["options"])


def test_large_amount_goes_to_underwriter():
    inp = good_input(requested_amount=15_000_000, monthly_revenue=10_000_000, monthly_expenses=7_000_000,
                     annual_revenue_reported=120_000_000)
    d = decide(PRODUCTS["WORKING"], inp, score(inp), term=36, purpose="working_capital")
    assert d.outcome == "MANUAL_REVIEW"
    assert d.recommendation


def test_tax_arrears_request_certificate_then_pass():
    inp = good_input(tax_arrears=64_000)
    first = decide(PRODUCTS["WORKING"], inp, score(inp), term=24, purpose="working_capital")
    assert first.outcome == "INFO_REQUESTED"
    assert first.requested_documents == ["tax_certificate"]
    second = decide(PRODUCTS["WORKING"], inp, score(inp), term=24, purpose="working_capital",
                    provided_documents={"tax_certificate"})
    assert second.outcome == "APPROVED"


def test_knockout_rules_reject():
    inp = good_input(max_delinquency_days_12m=120)
    d = decide(PRODUCTS["EXPRESS"], inp, score(inp), term=12, purpose="other")
    assert d.outcome == "REJECTED"
    assert d.reasons[0]["tips"]
    d2 = decide(PRODUCTS["EXPRESS"], good_input(), score(good_input()), term=12, purpose="other",
                egrul_status="LIQUIDATING")
    assert d2.outcome == "REJECTED"


def test_state_machine_rules():
    assert can_transition(Status.DRAFT, Status.SUBMITTED, Actor.CLIENT)
    assert not can_transition(Status.DRAFT, Status.APPROVED, Actor.CLIENT)
    assert not can_transition(Status.MANUAL_REVIEW, Status.APPROVED, Actor.CLIENT)
    assert can_transition(Status.MANUAL_REVIEW, Status.APPROVED, Actor.UNDERWRITER)
    with pytest.raises(TransitionError):
        ensure_transition(Status.DISBURSED, Status.CANCELLED, Actor.CLIENT)


def test_precheck_readiness_levels():
    good = readiness.evaluate(readiness.PrecheckAnswers(
        product=PRODUCTS["EXPRESS"], amount=1_000_000, term_months=24, business_age_months=48,
        monthly_revenue=1_500_000, monthly_expenses=1_000_000, existing_monthly_payments=0, industry="food"))
    bad = readiness.evaluate(readiness.PrecheckAnswers(
        product=PRODUCTS["EXPRESS"], amount=4_000_000, term_months=12, business_age_months=4,
        monthly_revenue=500_000, monthly_expenses=450_000, existing_monthly_payments=30_000, delinquency="serious"))
    assert good["level"] == "high"
    assert bad["level"] == "low"
    assert bad["blockers"] and bad["tips"]
    assert "не обещание" in good["disclaimer"]


def test_advisor_picks_invest_for_equipment():
    res = recommend(NeedProfile(purpose="equipment", amount=5_000_000, has_collateral=True, business_age_months=36))
    assert res["best"] == "INVEST"
    res2 = recommend(NeedProfile(purpose="cash_gap", amount=500_000, urgency="urgent"))
    assert res2["best"] in ("OVERDRAFT", "EXPRESS")
