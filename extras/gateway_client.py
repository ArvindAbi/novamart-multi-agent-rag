"""
gateway_client.py
=================
Stand-out extra: use the optional AgentCore Gateway (deploy Step 6) as an MCP
server, outside the agents.

  python extras/gateway_client.py --deploy   # run deploy_agentcore_gateway() first
  python extras/gateway_client.py            # list the gateway's tools and call each one

The graded agents keep their in-process @tool functions (the tests count them);
this script is the "separate MCP client integration" the README mentions. It
calls the tools directly, so it makes no model calls.
"""

import argparse
import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import boto3
import config
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SAMPLE_ARGUMENTS = {
    'check_order_status': {'order_id': 'ORD-27176'},
    'get_customer_tier':  {'customer_id': 'CUST-002'},
    'search_policies':    {'query': 'How long is the warranty on electronics for premium customers?'},
}


def find_gateway(ctrl) -> dict:
    for gw in ctrl.list_gateways().get('items', []):
        if gw['name'].startswith('novamart-support-'):
            return ctrl.get_gateway(gatewayIdentifier=gw['gatewayId'])
    sys.exit("No novamart-support-* gateway found - run with --deploy first")


def wait_for_targets(ctrl, gateway_id: str, timeout: int = 180) -> list:
    deadline = time.time() + timeout
    while True:
        targets = ctrl.list_gateway_targets(gatewayIdentifier=gateway_id).get('items', [])
        if targets and all(t['status'] in ('READY', 'FAILED') for t in targets):
            return targets
        if time.time() > deadline:
            return targets
        time.sleep(5)


def _short(text: str, limit: int = 300) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit] + ' ...'


async def call_tools(url: str) -> None:
    async with streamable_http_client(url) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print(f"\nMCP tools/list -> {len(tools)} tools")
            for t in tools:
                print(f"  {t.name:<45} {t.description[:60]}")

            for t in tools:
                short_name = t.name.split('___')[-1]
                arguments = SAMPLE_ARGUMENTS.get(short_name)
                if arguments is None:
                    continue
                result = await session.call_tool(t.name, arguments)
                text = ' '.join(getattr(c, 'text', '') for c in result.content)
                print(f"\nMCP tools/call {t.name} {json.dumps(arguments)}")
                print(f"  is_error={result.is_error}  ->  {_short(text)}")


def main() -> None:
    parser = argparse.ArgumentParser(description='AgentCore Gateway MCP client')
    parser.add_argument('--deploy', action='store_true',
                        help='create or update the gateway and its targets first')
    args = parser.parse_args()

    if args.deploy:
        import agent_orchestrator as ao
        print(json.dumps(ao.deploy_agentcore_gateway(), indent=2))

    ctrl = boto3.client('bedrock-agentcore-control', region_name=config.AWS_REGION)
    gateway = find_gateway(ctrl)
    print(f"Gateway {gateway['name']} ({gateway['gatewayId']}) status {gateway['status']}, "
          f"authorizer {gateway.get('authorizerType')}")
    print(f"URL {gateway['gatewayUrl']}")
    for t in wait_for_targets(ctrl, gateway['gatewayId']):
        print(f"  target {t['name']:<15} {t['status']}")
    asyncio.run(call_tools(gateway['gatewayUrl']))


if __name__ == '__main__':
    main()
