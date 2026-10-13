"""
create_dashboard.py
===================
Stand-out extra: a CloudWatch dashboard for the NovaMart agents.

  python extras/create_dashboard.py            # create or update
  python extras/create_dashboard.py --delete   # remove dashboard + metric filter

Widgets
  - Worker agent invocations over time (metric filter on the agent log lines,
    one metric per route_to_* tool)
  - Average latency per agent and per tool (Logs Insights on "tool done" lines)
  - Bedrock model invocations and latency: Haiku (orchestrator) vs Sonnet (workers)
  - Guardrail interventions by policy type, and guardrail invocations vs interventions

Sources: the agent logs in config.AGENT_LOG_GROUP (written by agent_observability.py
from local runs and the deployed runtime) and the AWS/Bedrock and
AWS/Bedrock/Guardrails metrics that Bedrock publishes on its own.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import boto3
import config

DASHBOARD_NAME = 'NovaMart-Agents'
FILTER_NAME    = 'novamart-agent-invocations'
NAMESPACE      = 'NovaMart/Agents'
REGION         = config.AWS_REGION
PERIOD         = 300

# Log line written for every finished tool call, e.g.
#   2026-10-14 00:13:09,621 INFO novamart.observability tool done  route_to_inventory_agent (10.27s)
INVOCATION_PATTERN = ('[date, time, level, logger, word1="tool", word2="done", '
                      'tool="route_to_*", duration]')

LATENCY_QUERY = (
    f"SOURCE '{config.AGENT_LOG_GROUP}' "
    "| fields @message "
    "| filter @message like /tool done  (route_to_|search_all_policies|retrieve_)/ "
    "| parse @message 'tool done  * (*s)' as tool, seconds "
    "| stats avg(seconds) as avg_seconds, max(seconds) as max_seconds, count(*) as calls by tool "
    "| sort avg_seconds desc"
)

REQUESTS_QUERY = (
    f"SOURCE '{config.AGENT_LOG_GROUP}' "
    "| fields @message "
    "| filter @message like /trace .* started/ "
    "| stats count(*) as customer_requests by bin(5m)"
)


def _widget(kind: str, x: int, y: int, w: int, h: int, props: dict) -> dict:
    return {'type': kind, 'x': x, 'y': y, 'width': w, 'height': h, 'properties': props}


def dashboard_body() -> dict:
    orch_model, worker_model = config.ORCHESTRATOR_MODEL_ID, config.WORKER_MODEL_ID
    return {'widgets': [
        _widget('text', 0, 0, 24, 2, {'markdown': (
            '## NovaMart multi-agent support\n'
            'Orchestrator (Claude Haiku 4.5) routes to Inventory, Policy (3 parallel KB '
            'retrievers), Refund and Communication agents (Claude Sonnet 4.5). Guardrail on '
            'every model call.')}),

        _widget('metric', 0, 2, 12, 6, {
            'title': 'Worker agent invocations (per 5 min)',
            'region': REGION, 'view': 'timeSeries', 'stat': 'Sum', 'period': PERIOD,
            'metrics': [[{'expression': f"SEARCH('{{{NAMESPACE},Agent}} "
                                        f"MetricName=\"AgentInvocations\"', 'Sum', {PERIOD})",
                          'id': 'agents', 'label': ''}]],
        }),
        _widget('log', 12, 2, 12, 6, {
            'title': 'Customer requests (per 5 min)',
            'region': REGION, 'view': 'timeSeries', 'query': REQUESTS_QUERY,
        }),

        _widget('log', 0, 8, 24, 6, {
            'title': 'Average latency per agent and tool (seconds)',
            'region': REGION, 'view': 'table', 'query': LATENCY_QUERY,
        }),

        _widget('metric', 0, 14, 12, 6, {
            'title': 'Model latency: Haiku (orchestrator) vs Sonnet (workers), ms',
            'region': REGION, 'view': 'timeSeries', 'stat': 'Average', 'period': PERIOD,
            'metrics': [
                ['AWS/Bedrock', 'InvocationLatency', 'ModelId', orch_model, {'label': 'Haiku 4.5'}],
                ['AWS/Bedrock', 'InvocationLatency', 'ModelId', worker_model, {'label': 'Sonnet 4.5'}],
            ],
        }),
        _widget('metric', 12, 14, 12, 6, {
            'title': 'Model invocations (per 5 min)',
            'region': REGION, 'view': 'timeSeries', 'stat': 'Sum', 'period': PERIOD,
            'metrics': [
                ['AWS/Bedrock', 'Invocations', 'ModelId', orch_model, {'label': 'Haiku 4.5'}],
                ['AWS/Bedrock', 'Invocations', 'ModelId', worker_model, {'label': 'Sonnet 4.5'}],
            ],
        }),

        _widget('metric', 0, 20, 12, 6, {
            'title': 'Guardrail interventions by policy type',
            'region': REGION, 'view': 'timeSeries', 'stat': 'Sum', 'period': PERIOD,
            'metrics': [[{'expression': "SEARCH('{AWS/Bedrock/Guardrails,GuardrailPolicyType,"
                                        "Operation} MetricName=\"InvocationsIntervened\"', "
                                        f"'Sum', {PERIOD})",
                          'id': 'policies', 'label': ''}]],
        }),
        _widget('metric', 12, 20, 12, 6, {
            'title': 'Guardrail checks vs interventions (all versions)',
            'region': REGION, 'view': 'timeSeries', 'stat': 'Sum', 'period': PERIOD,
            'metrics': [
                [{'expression': "SEARCH('{AWS/Bedrock/Guardrails,GuardrailArn,GuardrailVersion} "
                                f"MetricName=\"Invocations\"', 'Sum', {PERIOD})",
                  'id': 'checks', 'label': 'checks'}],
                [{'expression': "SEARCH('{AWS/Bedrock/Guardrails,GuardrailArn,GuardrailVersion} "
                                f"MetricName=\"InvocationsIntervened\"', 'Sum', {PERIOD})",
                  'id': 'blocked', 'label': 'interventions'}],
            ],
        }),
    ]}


def create() -> None:
    logs = boto3.client('logs', region_name=REGION)
    cw   = boto3.client('cloudwatch', region_name=REGION)

    logs.put_metric_filter(
        logGroupName=config.AGENT_LOG_GROUP,
        filterName=FILTER_NAME,
        filterPattern=INVOCATION_PATTERN,
        metricTransformations=[{
            'metricName':      'AgentInvocations',
            'metricNamespace': NAMESPACE,
            'metricValue':     '1',
            'dimensions':      {'Agent': '$tool'},
            'unit':            'Count',
        }],
    )
    print(f"Metric filter {FILTER_NAME} on {config.AGENT_LOG_GROUP} -> {NAMESPACE}/AgentInvocations")

    resp = cw.put_dashboard(DashboardName=DASHBOARD_NAME,
                            DashboardBody=json.dumps(dashboard_body()))
    for msg in resp.get('DashboardValidationMessages', []):
        print(f"  [validation] {msg.get('DataPath')}: {msg.get('Message')}")
    print(f"Dashboard {DASHBOARD_NAME}: https://{REGION}.console.aws.amazon.com/cloudwatch/home"
          f"?region={REGION}#dashboards/dashboard/{DASHBOARD_NAME}")


def delete() -> None:
    logs = boto3.client('logs', region_name=REGION)
    cw   = boto3.client('cloudwatch', region_name=REGION)
    try:
        logs.delete_metric_filter(logGroupName=config.AGENT_LOG_GROUP, filterName=FILTER_NAME)
        print(f"Deleted metric filter {FILTER_NAME}")
    except logs.exceptions.ResourceNotFoundException:
        pass
    cw.delete_dashboards(DashboardNames=[DASHBOARD_NAME])
    print(f"Deleted dashboard {DASHBOARD_NAME}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='NovaMart CloudWatch dashboard')
    parser.add_argument('--delete', action='store_true', help='remove the dashboard and metric filter')
    args = parser.parse_args()
    delete() if args.delete else create()
