"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

from lab8.db import connect
from lab8.durability import issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "single"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))

    def done(status: str, proposal: int = 0, reason: str | None = None) -> RunResult:
        trace.add("decision", {"status": status, "proposal_amount": proposal, "reason": reason})
        return finish(
            conn, shape=SHAPE, claim_id=claim_id, seed=seed, status=status,
            proposal_amount=proposal, budget=budget, trace=trace, error_reason=reason,
        )

    try:
        budget.add_tool(tool_cost())
        claim = get_claim_view(conn, claim_id)
        trace.add("claim", {"found": claim["found"], "has_order_id": bool(claim.get("order_id"))})
        if not claim["found"]:
            return done("failed", reason="unknown_claim")
        if not claim["order_id"]:
            return done("needs_info", reason="missing_order_id")

        # Ticket text cannot supply tool arguments or policy authority. The mock
        # model meters each decision; this bounded adapter permits only reads.
        reads: dict = {}

        def decide(seen: dict) -> dict:
            name = seen.get("last_tool")
            if name:
                reads[name] = seen["last_result"]
            complete(
                budget, seed=seed, purpose="decide",
                prompt=f"Read-only claim investigation; completed={','.join(reads)}",
            )
            if "lookup_order" not in reads:
                action = {"tool": "lookup_order", "args": {
                    "order_id": claim["order_id"], "principal_id": claim["principal_id"],
                }}
            elif not reads["lookup_order"]["visible"]:
                action = {"final": {"status": "investigated"}}
            elif "lookup_policy" not in reads:
                action = {"tool": "lookup_policy", "args": {}}
            elif "lookup_refund_history" not in reads:
                action = {"tool": "lookup_refund_history", "args": {
                    "order_id": claim["order_id"], "principal_id": claim["principal_id"],
                }}
            else:
                action = {"final": {"status": "investigated"}}
            trace.add("react", {"step": budget.model_calls, "action": action.get("tool", "final")})
            return action

        # Omit the ticket entirely from the model observation and trace.
        investigation = run_react(
            conn, budget, observation={"claim": {"claim_id": claim_id}},
            decide=decide, max_steps=8, worker=True,
        )
        if investigation["stopped"] != "final":
            return done("failed", reason="step_cap")
        order_view = reads.get("lookup_order")
        if order_view is None:
            return done("failed", reason="missing_order_observation")
        trace.add("lookup_order", order_view)
        if not order_view["visible"]:
            return done("escalated", reason=order_view["reason"])

        # Host owns money: recompute from the scoped order and current, effective
        # policies. compute_compensation checks is_current and effective_date;
        # neither a cited historical clause nor a model final can set the quote.
        budget.add_tool(tool_cost())
        quote = compute_compensation(conn, order_view["order"])
        proposal = int(quote["amount_vnd"])
        trace.add("quote", quote)
        if proposal <= 0:
            return done("denied", reason=quote["reason"])

        # Full quote, never history-netted: the host applies order caps once.
        trace.add("host_request", {"proposal_amount": proposal})
        trace.write()
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
        trace.add("issue_refund", {
            "ok": outcome["ok"], "reason": outcome["reason"], "conflict": outcome["conflict"],
        })
        if not outcome["ok"]:
            return done("failed" if outcome["conflict"] else "denied", proposal, outcome["reason"])
        return done("resolved", proposal)
    finally:
        conn.close()
