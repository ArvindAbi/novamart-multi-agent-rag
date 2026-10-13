# NovaMart Multi-Agent E-commerce RAG: submission

## Required deliverables

| Deliverable | Where |
|---|---|
| `src/agent_orchestrator.py` with all TODOs done (Tasks 2, 3, 4, 6) | [src/agent_orchestrator.py](src/agent_orchestrator.py) |
| Three Bedrock Knowledge Bases (Returns, Shipping, Warranty), created in the AWS Console on the stack's S3 Vectors bucket and indexes, Titan Embed Text v2, synced | IDs in `.env`, console screenshots [below](#knowledge-bases-in-the-aws-console) |
| Populated `.env` (KB IDs, AgentCore Runtime ARN, guardrail ID and numbered version) | [.env](.env), committed on purpose (resource IDs only, no credentials) |
| `python tests/test_agent.py all`: 120/120 | [screenshots/test_results_120_part1.png](screenshots/test_results_120_part1.png), [part 2 with the score](screenshots/test_results_120_part2.png) |
| `python src/agent_orchestrator.py test` results | screenshots and full output [below](#python-srcagent_orchestratorpy-test) |
| X-Ray Service Map after `python src/agent_orchestrator.py test` | [screenshots/xray_service_map_latest.png](screenshots/xray_service_map_latest.png) (after the run below), earlier one [screenshots/xray_service_map.png](screenshots/xray_service_map.png) |

## Evidence added after the first review

The first review asked for screenshots of `python src/agent_orchestrator.py test`, of each Knowledge Base in the AWS console (S3 Vectors backing store and a synced data source), and of the AgentCore deployment.

### `python src/agent_orchestrator.py test`

Run on 14 October 2026 against the deployed stack. Full output: [test_outputs/agent_orchestrator_test.txt](test_outputs/agent_orchestrator_test.txt).

| Scenario | Routing | Result | Screenshot |
|---|---|---|---|
| Return ORD-27176 (CUST-001) | Orchestrator → Inventory → Refund → Communication | Approved (Premium, 12 days, 60-day window), return reference RET-D37D3719 | [orchestrator_test_1_start_and_return.png](screenshots/orchestrator_test_1_start_and_return.png) |
| Return policy for premium customers (CUST-002) | Orchestrator → Policy (3 KB retrievers in parallel) → Communication | 60-day window and Premium benefits from the policy text | [orchestrator_test_3_policy_parallel_retrieval.png](screenshots/orchestrator_test_3_policy_parallel_retrieval.png) |
| 5 items at $29.99 with 10% off (CUST-003) | Orchestrator → Communication | $134.96 (rounded only at the end); X-Ray trace published | [orchestrator_test_5_math_result.png](screenshots/orchestrator_test_5_math_result.png) |

X-Ray Service Map taken right after this run: [xray_service_map_latest.png](screenshots/xray_service_map_latest.png) (NovaMart-Orchestrator connected to InventoryAgent, RefundAgent, PolicyAgent, CommunicationAgent and KnowledgeBase:returns / shipping / warranty).

### Knowledge Bases in the AWS console

All three are listed as Available, type Unstructured vector store: [kb_list.png](screenshots/kb_list.png).

| KB | Overview and data source | Embeddings model and S3 Vectors store | Sync history |
|---|---|---|---|
| novamart-returns-policy-kb (CDNCSTNCIX) | [kb_returns_page.png](screenshots/kb_returns_page.png) | [kb_returns_embeddings_and_vector_store.png](screenshots/kb_returns_embeddings_and_vector_store.png): Titan Text Embeddings v2, 1024; Amazon S3 Vectors, index `udacity-agentcore-vectors-064040034215-756655e0/index/returns-policy-index` | [kb_returns_sync_history.png](screenshots/kb_returns_sync_history.png): Complete, 2 scanned, 2 added, 0 failed |
| novamart-shipping-policy-kb (I8RL0EB5DP) | [kb_shipping_page.png](screenshots/kb_shipping_page.png) | [kb_shipping_embeddings_and_vector_store.png](screenshots/kb_shipping_embeddings_and_vector_store.png): same bucket, `shipping-policy-index` | [kb_shipping_sync_history.png](screenshots/kb_shipping_sync_history.png): Complete, 2 scanned, 2 added, 0 failed |
| novamart-warranty-policy-kb (YW64YVOI4R) | [kb_warranty_overview_and_sync.png](screenshots/kb_warranty_overview_and_sync.png) | [kb_warranty_embeddings_and_vector_store.png](screenshots/kb_warranty_embeddings_and_vector_store.png): same bucket, `warranty-policy-index` | [kb_warranty_sync_history.png](screenshots/kb_warranty_sync_history.png): Complete, 2 scanned, 2 added, 0 failed |

`udacity-agentcore-vectors-064040034215-756655e0` is the stack's VectorStoreBucket (`python config.py`, "Vector Bucket").

### AgentCore deployment

| Resource | State | Screenshot |
|---|---|---|
| AgentCore Runtime `udacity_agentcore_runtime` (graded, IAM auth) and `udacity_agentcore_web` (extra, Cognito JWT) | Ready | [agentcore_runtimes.png](screenshots/agentcore_runtimes.png) |
| AgentCore Memory `udacity_agentcore_memory` | Active, 1 strategy (session summary), 7-day event expiry | [agentcore_memory.png](screenshots/agentcore_memory.png) |
| Bedrock Guardrail `udacity-agentcore-guardrail` (magc8wpzgo9e, version 1) | Ready | [guardrail_overview.png](screenshots/guardrail_overview.png), [content filters](screenshots/guardrail_content_filters.png), [prompt attacks](screenshots/guardrail_prompt_attacks.png), [denied topics](screenshots/guardrail_denied_topics.png), [PII](screenshots/guardrail_pii.png) |
| CloudFormation stacks `udacity-agentcore` (foundation) and `AgentCore-udacity-default` (runtime, created by the AgentCore CLI) | CREATE_COMPLETE / UPDATE_COMPLETE | [cloudformation_stacks.png](screenshots/cloudformation_stacks.png) |
| AgentCore Gateway `novamart-support-756655e0` (optional Step 6) | Ready | [agentcore_gateway.png](screenshots/agentcore_gateway.png) |

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
