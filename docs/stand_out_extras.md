# Stand-out extras

Everything the rubric's "Suggestions to Make Your Project Stand Out" asks for, plus the optional AgentCore Gateway step (deploy Step 6) from the README. The graded work (`src/agent_orchestrator.py` TODOs, the three Knowledge Bases, `.env`, the two screenshots) does not depend on any of this; the 120-point test suite passes with or without it.

| # | Extra | Where | Details |
|---|---|---|---|
| 1 | Adversarial guardrail tests | `extras/guardrail_adversarial.py`, `create_guardrail()` | [guardrail_adversarial_tests.md](guardrail_adversarial_tests.md) |
| 2 | Persistent conversation memory in a DynamoDB `agent-sessions` table | `ConversationMemoryHook` and `DynamoDBSessionRepository` in `src/agent_orchestrator.py`, `extras/session_table.py`, `extras/session_memory_demo.py` | below |
| 3 | CloudWatch dashboard | `extras/create_dashboard.py` | below |
| 4 | Cognito sign-in and a web page connected to AgentCore Runtime | `extras/web_setup.py`, `extras/web_server.py`, `extras/web/` | [web_frontend.md](web_frontend.md) |
| 5 | AgentCore Gateway with Lambda tool targets (README Step 6) | `extras/gateway/`, `extras/gateway_setup.py`, `extras/gateway_client.py` | below |

## 2. Persistent conversation memory

The OrchestratorAgent is built once and serves every session, so the starter's design either mixes customers' histories or forgets everything between processes. `ConversationMemoryHook` fixes both: at the start of each request it reads the session id from the `[Session ID: ...]` prefix, loads that session's earlier messages from DynamoDB through Strands' `RepositorySessionManager`, and saves every new message.

- Strands 1.60 has no `DynamoDbSessionStorage` class, so `DynamoDBSessionRepository` implements Strands' own `SessionRepository` interface on DynamoDB (one table, keys `session_id` + `record`, 7-day TTL like the AgentCore Memory events).
- A message the guardrail blocked is stored only in its redacted form (`[User input redacted.]`), never the original text (checked with a card number: nothing stored).
- It only switches on when `AGENT_SESSION_TABLE` is set, and DynamoDB errors are logged, never shown to the customer.
- AgentCore Memory (Task 4) keeps session summaries in the cloud; this keeps the raw turns next to the agent. They complement each other.

Demo (`python extras/session_memory_demo.py`, screenshot `screenshots/session_memory_demo.png`): turn 1 asks "How much does expedited shipping cost?", turn 2 builds a brand-new agent graph and asks "Will I have to pay that on my next order?". The new Orchestrator loaded turn 1 from DynamoDB, understood "that" as the $9.99 expedited fee, checked the customer's tier and answered that Premium customers get expedited shipping free.

## 3. CloudWatch dashboard `NovaMart-Agents`

`python extras/create_dashboard.py` creates:

- **Worker agent invocations over time**: a metric filter on the agent log lines (`tool done  route_to_<agent>`) publishes `NovaMart/Agents AgentInvocations` per agent.
- **Customer requests over time** and **average latency per agent and tool**: Logs Insights queries on the agent log group.
- **Model latency and invocations**: Haiku 4.5 (orchestrator) vs Sonnet 4.5 (workers) from `AWS/Bedrock`.
- **Guardrail interventions by policy type** and **checks vs interventions**: from `AWS/Bedrock/Guardrails`.

Screenshot: `screenshots/cloudwatch_dashboard.png`.

## 5. AgentCore Gateway

The starter's `deploy_agentcore_gateway()` skips itself until three Lambda tool functions exist. `extras/gateway_setup.py` deploys them to match the tool schemas the starter declares:

| Target | Tool | Lambda |
|---|---|---|
| orders-api | `check_order_status(order_id)` | `novamart-orders-api` (filtered scan, since the Orders key also needs customer_id) |
| policy-api | `search_policies(query)` | `novamart-policy-api` (Returns, Shipping and Warranty KBs in parallel) |
| customers-api | `get_customer_tier(customer_id)` | `novamart-customers-api` |

With `ORDERS_FUNCTION`, `POLICY_FUNCTION` and `CUSTOMERS_FUNCTION` in `.env`, deploy Step 6 creates the MCP gateway and the three targets. The gateway calls the Lambdas with the stack's runtime role, which has no Lambda permission of its own, so each function has a resource policy allowing that role.

The graded agents keep their in-process tools (the tests count them). `python extras/gateway_client.py` is the separate MCP client the README mentions: it lists the gateway's tools and calls each one (screenshot `screenshots/gateway_mcp_client.png`). The starter creates the gateway without an authorizer, so its URL is open while it exists; it only serves the mock data and is deleted at cleanup.

## Cleanup

```bash
python extras/cleanup_extras.py --yes
```
```bash
python infrastructure/cleanup.py --yes --disable-transaction-search
```
