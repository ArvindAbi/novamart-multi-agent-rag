"""
session_memory_demo.py
======================
Stand-out extra: show the Orchestrator's persistent conversation memory.

  python extras/session_memory_demo.py

Turn 1 asks a policy question. Turn 2 builds a brand-new agent graph (as after
a restart, or in another runtime instance) and asks a follow-up that only makes
sense with turn 1 ("that"). The new Orchestrator loads turn 1 from the DynamoDB
agent-sessions table through ConversationMemoryHook.

Needs AGENT_SESSION_TABLE in .env (extras/session_table.py).
"""

import contextlib
import io
import os
import sys
import textwrap
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import agent_orchestrator as ao
from agent_observability import tracer, flush_logs

CUSTOMER_ID = 'CUST-001'
TURNS = [
    "How much does expedited shipping cost?",
    "Will I have to pay that on my next order?",
]


def main() -> None:
    if not ao.SESSION_TABLE:
        sys.exit("AGENT_SESSION_TABLE is not set in .env - run extras/session_table.py first")
    session_id = uuid.uuid4().hex[:8]
    print(f"Session {session_id} | customer {CUSTOMER_ID} | table {ao.SESSION_TABLE}")

    for n, question in enumerate(TURNS, 1):
        orchestrator = ao.build_agent_graph()      # new graph each turn: no history in memory
        print('=' * 100)
        print(f"Turn {n} (new agent graph, {len(orchestrator.messages)} messages in memory)")
        print(f"  Customer : {question}")
        prompt = f"[Session ID: {session_id}] [Customer ID: {CUSTOMER_ID}] {question}"
        with contextlib.redirect_stdout(io.StringIO()):
            with tracer.trace_request(session_id, CUSTOMER_ID, question):
                orchestrator(prompt)
        state = ao._read_workflow_state(session_id) or {}
        reply = ao._strip_xml_tags(state.get('communication_agent', ''))
        user_turns = [m for m in orchestrator.messages if m['role'] == 'user'
                      and any('[Session ID:' in b.get('text', '') for b in m['content'])]
        print(f"  Orchestrator history now holds {len(user_turns)} customer message(s) "
              f"from this session")
        print("  Reply    : " + textwrap.fill(' '.join(reply.split()), width=100,
                                              subsequent_indent=' ' * 13))

    items = ao.dynamodb.Table(ao.SESSION_TABLE).query(
        KeyConditionExpression=ao.Key('session_id').eq(session_id))['Items']
    print('=' * 100)
    print(f"DynamoDB {ao.SESSION_TABLE}: {len(items)} records for session {session_id} "
          f"({sum(i['record'].startswith('MESSAGE#') for i in items)} messages)")
    flush_logs()


if __name__ == '__main__':
    main()
