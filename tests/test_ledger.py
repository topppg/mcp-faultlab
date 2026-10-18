import pytest

from mcp_faultlab.ledger import Ledger
from mcp_faultlab.model import Call


def charge(ledger, ident="1", **extra):
    return ledger.execute(Call(ident, "ledger.charge", {"operation": "order-1", "amount": 10, **extra}))


def test_naive_retries_duplicate_side_effect_and_keyed_retries_do_not():
    ledger = Ledger()
    charge(ledger)
    charge(ledger, "2")
    assert ledger.snapshot()["duplicate_effects"] == 1
    ledger = Ledger()
    charge(ledger, idempotency_key="order-1")
    second = charge(ledger, "2", idempotency_key="order-1")
    assert second["structuredContent"]["deduplicated"]
    assert ledger.snapshot()["side_effects"] == 1
    assert charge(ledger, "3", idempotency_key="order-1", amount=11)["isError"]


@pytest.mark.parametrize("patch", [{"amount": True}, {"amount": -1}, {"operation": ""},
                                  {"idempotency_key": ""}, {"extra": 3}])
def test_invalid_charges_do_not_commit(patch):
    ledger = Ledger()
    assert charge(ledger, **patch)["isError"]
    assert not ledger.entries


def test_lookup_and_snapshot_are_isolated():
    ledger = Ledger()
    charge(ledger)
    response = ledger.execute(Call("2", "ledger.lookup", {"operation": "order-1"}))
    response["structuredContent"]["entries"][0]["amount"] = 999
    assert ledger.snapshot()["total_amount"] == 10
