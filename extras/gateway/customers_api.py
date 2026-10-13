"""
Lambda target for the AgentCore Gateway tool `get_customer_tier` (target customers-api).

Input (tool arguments):  {"customer_id": "CUST-001"}
"""

import os
from decimal import Decimal

import boto3

TABLE = boto3.resource('dynamodb').Table(os.environ['CUSTOMERS_TABLE'])


def _plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def handler(event, context):
    customer_id = (event or {}).get('customer_id', '').strip()
    if not customer_id:
        return {'error': 'customer_id is required'}
    item = TABLE.get_item(Key={'customer_id': customer_id}).get('Item')
    if not item:
        return {'error': f"Customer {customer_id} not found"}
    return {k: _plain(v) for k, v in item.items()}
