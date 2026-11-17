"""Shape C — orchestrator plus read-only investigators. Student work.

1. Build a handoff with `lab8.handoff.make_handoff`. Allowed tools are read-only.
   Never put parent_secret, raw headers, or the full claim row into facts.
2. `lab8.runtime.run_readonly_investigators` runs those tools.
3. The orchestrator quotes from the investigator's order view and calls
   `durability.issue_refund`. Investigators have no write registry.
   Pass the full quote; the host subtracts earlier refunds on the same order.
   `lookup_refund_history` is a read-only tool you may hand to an investigator.
4. Trace the sanitized handoff, not the parent context.

An LLM summary of the parent context is not a sanitizer. Use the allowlist.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "orchestrator"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    run_id = make_run_id(SHAPE, claim_id, seed)
    trace = Trace(run_id)

    def done(status: str, proposal: int, reason: str | None) -> RunResult:
        complete(budget, seed=seed, purpose="draft", prompt=f"status={status}")
        trace.add("decision", {"status": status, "proposal_amount": int(proposal), "reason": reason})
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    # Step 1: Read allowlisted claim view. Never parse or trace raw ticket/secrets.
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim["found"]:
        trace.add("claim", {"found": False})
        return done("failed", 0, "unknown_claim")
    trace.add("claim", {"found": True, "has_order_id": bool(claim["order_id"])})

    # Step 2: Missing order_id -> needs_info. Never guess from ticket text.
    if not claim["order_id"]:
        return done("needs_info", 0, "missing_order_id")

    # Step 3: Build sanitized typed handoff for read-only investigators.
    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="investigate_order_and_policy",
        facts={},
        allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
    )
    trace.add("handoff", safe_dump(handoff))

    # Step 4: Dispatch read-only investigators.
    investigated = run_readonly_investigators(
        conn, budget, handoff, principal_id=claim["principal_id"]
    )
    order_view = investigated["tools"].get("lookup_order", {})
    trace.add(
        "investigator",
        {
            "lookup_order": order_view,
            "policy_count": len((investigated["tools"].get("lookup_policy") or {}).get("policies") or []),
        },
    )

    # Step 5: Check if order is visible to the principal.
    if not order_view.get("visible"):
        return done("escalated", 0, order_view.get("reason"))

    # Step 6: Quote compensation from investigator results (or recompute if needed).
    quote_payload = investigated["tools"].get("compute_compensation")
    if not quote_payload:
        budget.add_tool(tool_cost())
        quote_payload = compute_compensation(conn, order_view["order"])
    proposal = int(quote_payload["amount_vnd"])
    trace.add("quote", quote_payload)

    # Step 7: Zero quote -> denied without calling host writer.
    if proposal <= 0:
        return done("denied", 0, quote_payload.get("reason"))

    # Step 8: Pass full quote to host gate. Propagate InjectedCrash after flushing trace.
    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    trace.add(
        "issue_refund",
        {
            "ok": outcome["ok"],
            "reason": outcome["reason"],
            "conflict": outcome["conflict"],
        },
    )

    if not outcome["ok"]:
        status = "failed" if outcome["conflict"] else "denied"
        return done(status, proposal, outcome["reason"])

    # Step 9: Successfully committed refund.
    return done("resolved", proposal, None)
