"""
Lambda target for the AgentCore Gateway tool `search_policies` (target policy-api).

Input (tool arguments):  {"query": "What is the return window for premium customers?"}
Searches the Returns, Shipping and Warranty Knowledge Bases in parallel, the same
fan-out the PolicyAgent does in-process, and returns the top passages per domain.
"""

import os
from concurrent.futures import ThreadPoolExecutor

import boto3

KB_IDS = {
    'Returns':  os.environ['RETURNS_KB_ID'],
    'Shipping': os.environ['SHIPPING_KB_ID'],
    'Warranty': os.environ['WARRANTY_KB_ID'],
}
CLIENT = boto3.client('bedrock-agent-runtime')


def _retrieve(kb_id: str, query: str) -> list:
    response = CLIENT.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={'text': query},
        retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': 3}},
    )
    return [{
        'text':   r.get('content', {}).get('text', ''),
        'source': r.get('location', {}).get('s3Location', {}).get('uri', ''),
        'score':  round(float(r.get('score', 0.0)), 4),
    } for r in response.get('retrievalResults', [])]


def handler(event, context):
    query = (event or {}).get('query', '').strip()
    if not query:
        return {'error': 'query is required'}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {domain: executor.submit(_retrieve, kb_id, query)
                   for domain, kb_id in KB_IDS.items()}
    return {'query': query, 'results': {domain: f.result() for domain, f in futures.items()}}
