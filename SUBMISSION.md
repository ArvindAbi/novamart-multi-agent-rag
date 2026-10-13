# NovaMart Multi-Agent E-commerce RAG: submission

## Required deliverables

| Deliverable | Where |
|---|---|
| `src/agent_orchestrator.py` with all TODOs done (Tasks 2, 3, 4, 6) | [src/agent_orchestrator.py](src/agent_orchestrator.py) |
| Three Bedrock Knowledge Bases (Returns, Shipping, Warranty), created in the AWS Console on the stack's S3 Vectors bucket and indexes, Titan Embed Text v2, synced | IDs in `.env` |
| Populated `.env` (KB IDs, AgentCore Runtime ARN, guardrail ID and numbered version) | [.env](.env), committed on purpose (resource IDs only, no credentials) |
| `python tests/test_agent.py all`: 120/120 | [screenshots/test_results_120_part1.png](screenshots/test_results_120_part1.png), [part 2 with the score](screenshots/test_results_120_part2.png) |
| X-Ray Service Map after `python src/agent_orchestrator.py test` | [screenshots/xray_service_map.png](screenshots/xray_service_map.png) |

The three end-to-end scenarios were run with `python src/agent_orchestrator.py test` against the deployed system:

| Scenario | Routing | Result |
|---|---|---|
| Return ORD-27176 (CUST-001) | Orchestrator → Inventory → Refund → Communication | Approved, Premium 60-day window, return reference issued |
| Return policy for premium customers | Orchestrator → Policy (3 parallel KB retrievers) → Communication | 60-day window and Premium benefits from the policy text |
| 5 items at $29.99 with 10% off | Orchestrator → Communication | $134.96 (rounded only at the end) |

## Implementation notes

- Worker agents (and the three retrievers) are built once and reused, so each `route_to_*` tool clears its worker's message history before calling it. Otherwise one customer's facts and decisions would carry into the next request.
- The Orchestrator runs its tools one at a time (Strands `SequentialToolExecutor`). With the default parallel execution it sometimes started a worker before `initialize_session` had created the WorkflowState row.
- `check_order_status` adds `days_since_order`, because the model does not know today's date.
- The guardrail's pricing-negotiation topic is defined narrowly (bargaining for a lower price). The first definition blocked the project's own maths question; the final one allows it while still blocking haggling and price matching. Checked with the ApplyGuardrail API before deploying.

## Stand-out extras

All four rubric suggestions plus the optional AgentCore Gateway (README Step 6) are done; see [docs/stand_out_extras.md](docs/stand_out_extras.md).

| Extra | Docs | Screenshots |
|---|---|---|
| Adversarial guardrail tests (prompt injection, jailbreak, competitor, haggling, legal threat, card number, SSN, insults, output masking) | [docs/guardrail_adversarial_tests.md](docs/guardrail_adversarial_tests.md) | `guardrail_adversarial_*.png` |
| Persistent conversation memory in a DynamoDB `agent-sessions` table | [docs/stand_out_extras.md](docs/stand_out_extras.md) | `session_memory_demo_*.png` |
| CloudWatch dashboard (invocations, latency per agent, model latency, guardrail interventions) | [docs/stand_out_extras.md](docs/stand_out_extras.md) | `cloudwatch_dashboard_*.png` |
| Cognito sign-in and a web page on a JWT-protected AgentCore runtime | [docs/web_frontend.md](docs/web_frontend.md) | `web_*.png` |
| AgentCore Gateway with Lambda tool targets, used through an MCP client | [docs/stand_out_extras.md](docs/stand_out_extras.md) | `gateway_mcp_client.png` |

Extra X-Ray views: `xray_traces_list.png`, `xray_trace_policy_question.png`.
