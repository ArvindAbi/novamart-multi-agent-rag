# Web frontend with Cognito sign-in

This covers the fourth stand-out suggestion: customer authentication with Amazon Cognito and a web page connected to the AgentCore Runtime.

## How it fits together

```
Browser (extras/web)                    local server (extras/web_server.py)          AWS
-------------------                     -----------------------------------          ---
Sign in  ──────────────────────────────────────────────────────────────────────►  Cognito hosted login
         ◄──── authorization code (PKCE) ─────────────────────────────────────────  (user pool novamart-customers)
code + verifier ───────────────────────────────────────────────────────────────►  Cognito /oauth2/token
         ◄──── ID token (contains custom:customer_id) ────────────────────────────
POST /api/chat  ── Bearer ID token ──►  POST .../runtimes/<web runtime>/invocations  ──►  AgentCore Runtime
                                        Authorization: Bearer <same token>                udacity_agentcore_web
                                        customer_id taken from the token                  JWT authorizer checks
                                                                                          signature, expiry, audience
         ◄──────────── reply ─────────  ◄────────────────── {"result": ...} ─────────────  same five agents
```

- **Two runtimes.** The graded runtime `udacity_agentcore_runtime` keeps AWS IAM (SigV4) auth, so the tests, `python src/agent_orchestrator.py invoke` and the AgentCore CLI keep working. `extras/web_setup.py` creates a second runtime, `udacity_agentcore_web`, from the same code package, role and environment, with a Cognito JWT authorizer. It is created with the control-plane API so the starter's `agentcore/` project stays unchanged.
- **Who the customer is.** The page never sends a customer id. The local server reads `custom:customer_id` from the ID token, and forwards that same token to the runtime, which rejects it unless Cognito signed it for this app client and it has not expired. A forged token therefore never reaches the agents.
- **No AWS keys in the browser or the local server.** The only credential in the request is the customer's own short-lived token (60 minutes).
- **Conversation memory.** Each browser chat keeps one session id, so the DynamoDB session store (extra 2) keeps the conversation across messages.
- Page and API are served from the same origin (`http://localhost:8080`), so no CORS setup is needed.

## Checks done without signing in

| Request to the web runtime | Result |
|---|---|
| No token | HTTP 401 |
| Forged token (made-up signature) | HTTP 401 |
| Cognito hosted login URL | HTTP 302 to the sign-in form |

## Run it

1. Create the user pool, app client, login domain and web runtime (already done in this account):
   ```bash
   python extras/web_setup.py
   ```
2. Create a customer login. Use your own password (at least 10 characters with upper case, lower case and a number). The user pool id is printed by step 1.
   ```bash
   aws cognito-idp admin-create-user --region us-east-1 --user-pool-id <pool id> --username alice --user-attributes Name=email,Value=alice@example.com Name=custom:customer_id,Value=CUST-001 --message-action SUPPRESS
   ```
   ```bash
   aws cognito-idp admin-set-user-password --region us-east-1 --user-pool-id <pool id> --username alice --password '<your password>' --permanent
   ```
3. Start the page and open http://localhost:8080:
   ```bash
   python extras/web_server.py
   ```
4. Click **Sign in**, log in as `alice`, and chat. The header shows the signed-in email and customer id.

## Screenshots

`screenshots/web_*.png`: the signed-out and signed-in page, tier and order lookups, a return already in progress, a denied return, a follow-up question that relies on conversation memory, and a competitor question blocked by the guardrail.

## Removing it

```bash
python extras/web_setup.py --delete
```
