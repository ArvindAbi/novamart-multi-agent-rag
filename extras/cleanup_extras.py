"""
cleanup_extras.py
=================
Remove everything the stand-out extras created. Run it before
infrastructure/cleanup.py: the sessions-table policy sits on the stack's
runtime role, and CloudFormation cannot delete a role that still has it.

  python extras/cleanup_extras.py          # dry run - lists what would be deleted
  python extras/cleanup_extras.py --yes    # deletes it

Covers: the web runtime and Cognito user pool (web_setup.py), the gateway tool
Lambdas and their role (gateway_setup.py), the agent-sessions table and its role
policy (session_table.py) and the CloudWatch dashboard + metric filter
(create_dashboard.py). The gateway itself is deleted by infrastructure/cleanup.py.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ('web runtime udacity_agentcore_web and Cognito user pool novamart-customers', 'web_setup.py'),
    ('gateway tool Lambdas novamart-*-api and role novamart-gateway-lambda-role', 'gateway_setup.py'),
    ('DynamoDB table udacity-agentcore-agent-sessions and its policy on the runtime role', 'session_table.py'),
    ('CloudWatch dashboard NovaMart-Agents and its metric filter', 'create_dashboard.py'),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remove the stand-out extras')
    parser.add_argument('--yes', action='store_true', help='actually delete (default is a dry run)')
    args = parser.parse_args()

    for label, script in STEPS:
        if not args.yes:
            print(f"[dry run] would delete: {label}")
            continue
        print(f"\n== {label}")
        subprocess.run([sys.executable, os.path.join(HERE, script), '--delete'], check=False)

    if not args.yes:
        print("\nRun again with --yes to delete, then run infrastructure/cleanup.py --yes")
