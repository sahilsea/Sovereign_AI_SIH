"""Tests for the deterministic calculator (harness/calculator.py).

Verifies:
1. Natural-language arithmetic is recognised and evaluated exactly, with steps.
2. Document questions containing numbers/dashes are NOT treated as arithmetic.
3. Unsafe or runaway input is refused (no eval, exponent/size limits).
4. run_query answers arithmetic without calling any model.
5. The agent's `calculate` tool returns results and steps.
"""

import pytest

from contracts import AskRequest, Label, Passage, Principal, Tier
from harness.agent_tools import ToolContext, call_tool
from harness.calculator import CalculationError, calculate
from harness.runner import run_query
from trust.conversations import init_conversations_table
from trust.ledger import init_ledger_table
from trust.reports import init_reports_table


@pytest.mark.parametrize("q,result,n_steps", [
    ("add 2 + 2", 4, 1),
    ("add 2 and 3", 5, 1),
    ("what is 15% of 2400?", 360, 2),
    ("sum of 4, 5 and 6", 15, 2),
    ("calculate (3+4)*2^3", 56, 3),
    ("5 plus 3 times 2", 11, 2),        # precedence respected
    ("square root of 144", 12, 1),
    ("12 x 4", 48, 1),
    ("2,400 * 1.18", 2832, 1),
    ("sin(30)", 0.5, 1),                # degrees
])
def test_recognises_and_evaluates(q, result, n_steps):
    calc = calculate(q)
    assert calc is not None
    assert calc["result"] == pytest.approx(result)
    assert len(calc["steps"]) == n_steps


@pytest.mark.parametrize("q", [
    "What is 201-XV-01?",
    "What did the Q2 2025 procurement audit find?",
    "2025",
    "What must personnel do during a toxic gas release at CDU-2?",
    "Calculate the volumetric flow rate through a 150 mm pipe at 2 m/s",  # word problem -> code path
    "__import__('os').system('ls')",
])
def test_non_arithmetic_is_left_alone(q):
    assert calculate(q) is None


@pytest.mark.parametrize("q", ["10 / 0", "2**99999", "factorial(500)"])
def test_unsafe_or_invalid_is_refused(q):
    with pytest.raises(CalculationError):
        calculate(q)


class ExplodingAgent:
    """Any model call fails the test: arithmetic must not reach a model."""
    def classify_intent(self, *a, **k):
        raise AssertionError("model called for arithmetic")

    def draft(self, *a, **k):
        raise AssertionError("model called for arithmetic")


def test_run_query_answers_arithmetic_without_a_model(tmp_path):
    db = str(tmp_path / "c.db")
    for init in (init_ledger_table, init_reports_table, init_conversations_table):
        init(db)
    p = Principal(person_id="p1", name="P", job_title="Officer", grade="A", compartments=frozenset())
    corpus = [Passage(doc_id="d", page=1, text="unrelated text", label=Label(tier=Tier.PUBLIC))]
    res = run_query(AskRequest(question="add 2 + 2"), corpus, p, ExplodingAgent(), db)
    assert res.status == "answered"
    assert res.outcome == "computed"
    assert "**4**" in res.answer and "2 + 2 = 4" in res.answer

    res = run_query(AskRequest(question="10 / 0"), corpus, p, ExplodingAgent(), db)
    assert res.status == "abstained" and "division by zero" in res.answer


def test_agent_calculate_tool():
    p = Principal(person_id="p1", name="P", job_title="Officer", grade="A", compartments=frozenset())
    ctx = ToolContext(principal=p, corpus=[], agent=None)
    ok, observation, _ = call_tool(ctx, "calculate", {"expression": "(1200 + 1350 + 1100) / 3"})
    assert ok and "1216.66" in observation
    ok, observation, _ = call_tool(ctx, "calculate", {"expression": "open('x')"})
    assert not ok


@pytest.mark.parametrize("q,expected", [
    ("add 2 with 2 and then divide it by 593", 4 / 593),       # NOT 2 + 2/593
    ("add 10 and 5, then multiply by 3 and then square it", 2025),
    ("multiply 6 by 7 then subtract 2", 40),
    ("subtract 3 from 10", 7),
    ("add 100 with 50 then take 18% of it", 27),
])
def test_stepwise_phrasing_keeps_the_order_described(q, expected):
    assert calculate(q)["result"] == pytest.approx(expected)


def test_unknown_then_clause_is_not_guessed():
    assert calculate("add 2 with 2 and then email it to the manager") is None


class TranslatingAgent:
    """Classifier that translates words into a calculator expression."""
    last_intent_model = "fake-granite"

    def __init__(self, expression):
        self.last_calc_expression = expression

    def classify_intent(self, question, recent_context=""):
        return "calculation"

    def draft(self, *a, **k):
        raise AssertionError("document drafting must not run for a calculation")


def _db(tmp_path):
    db = str(tmp_path / "t.db")
    for init in (init_ledger_table, init_reports_table, init_conversations_table):
        init(db)
    return db


def test_model_translated_calculation_is_computed_by_the_calculator(tmp_path):
    p = Principal(person_id="p1", name="P", job_title="Officer", grade="A", compartments=frozenset())
    res = run_query(AskRequest(question="how big is a 150 mm pipe's flow at 2 m/s"), [], p,
                    TranslatingAgent("pi*(0.150/2)**2*2"), _db(tmp_path))
    assert res.outcome == "computed"
    assert res.model_used == "fake-granite"
    assert "Interpreted as" in res.answer and "0.035343" in res.answer
    assert "only translated your words" in res.verification_note


def test_invalid_translation_falls_back_to_code_path(tmp_path):
    p = Principal(person_id="p1", name="P", job_title="Officer", grade="A", compartments=frozenset())
    res = run_query(AskRequest(question="some tricky numeric thing"), [], p,
                    TranslatingAgent("import os"), _db(tmp_path))
    # TranslatingAgent has no draft_code, so the code path abstains honestly.
    assert res.status == "abstained" and "sandboxed code execution" in res.answer
