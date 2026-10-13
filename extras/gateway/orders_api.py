"""
Lambda target for the AgentCore Gateway tool `check_order_status` (target orders-api).

Input (tool arguments):  {"order_id": "ORD-27176"}
The gateway's tool schema only passes the order id, while the Orders table key is
customer_id + order_id, so the order is found with a filtered scan (the table is small).
"""

import json
import os
from datetime import date
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

TABLE = boto3.resource('dynamodb').Table(os.environ['ORDERS_TABLE'])


def _plain(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def handler(event, context):
    order_id = (event or {}).get('order_id', '').strip()
    if not order_id:
        return {'error': 'order_id is required'}

    scan = {'FilterExpression': Attr('order_id').eq(order_id)}
    while True:
        page = TABLE.scan(**scan)
        if page.get('Items'):
            order = _plain(page['Items'][0])
            try:
                order['days_since_order'] = (date.today()
                                             - date.fromisoformat(order['order_date'])).days
            except (KeyError, ValueError):
                pass
            return order
        if 'LastEvaluatedKey' not in page:
            return {'error': f"Order {order_id} not found"}
        scan['ExclusiveStartKey'] = page['LastEvaluatedKey']
