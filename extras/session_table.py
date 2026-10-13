"""
session_table.py
================
Stand-out extra: the DynamoDB `agent-sessions` table behind the Orchestrator's
persistent conversation memory (see ConversationMemoryHook in agent_orchestrator.py).

  python extras/session_table.py            # create table + runtime role permission
  python extras/session_table.py --delete   # remove both

After creating it, add AGENT_SESSION_TABLE=<table name> to .env (local runs) and
re-run the deploy command so the runtime gets the same variable.

The AgentCore runtime role from the CloudFormation stack only allows the three
project tables, so an inline policy for this table is added to that role. Delete it
(this script's --delete) before deleting the stack.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import boto3
import config

TABLE_NAME  = f"{config.PROJECT_NAME}-agent-sessions"
POLICY_NAME = 'NovaMartAgentSessionsAccess'
ROLE_NAME   = config.AGENTCORE_ROLE_ARN.split('/')[-1]


def create() -> None:
    ddb = boto3.client('dynamodb', region_name=config.AWS_REGION)
    iam = boto3.client('iam')
    try:
        ddb.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{'AttributeName': 'session_id', 'AttributeType': 'S'},
                                  {'AttributeName': 'record',     'AttributeType': 'S'}],
            KeySchema=[{'AttributeName': 'session_id', 'KeyType': 'HASH'},
                       {'AttributeName': 'record',     'KeyType': 'RANGE'}],
            BillingMode='PAY_PER_REQUEST',
            Tags=[{'Key': 'project', 'Value': config.PROJECT_NAME}],
        )
        print(f"Creating table {TABLE_NAME}...")
    except ddb.exceptions.ResourceInUseException:
        print(f"Table {TABLE_NAME} already exists")
    ddb.get_waiter('table_exists').wait(TableName=TABLE_NAME)
    ttl = ddb.describe_time_to_live(TableName=TABLE_NAME)['TimeToLiveDescription']
    if ttl.get('TimeToLiveStatus') in (None, 'DISABLED'):
        ddb.update_time_to_live(TableName=TABLE_NAME,
                                TimeToLiveSpecification={'Enabled': True, 'AttributeName': 'ttl'})
    table_arn = ddb.describe_table(TableName=TABLE_NAME)['Table']['TableArn']

    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps({
            'Version': '2012-10-17',
            'Statement': [{
                'Effect':   'Allow',
                'Action':   ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem',
                             'dynamodb:Query', 'dynamodb:DeleteItem'],
                'Resource': table_arn,
            }],
        }),
    )
    print(f"Table ready: {table_arn} (TTL on `ttl`)")
    print(f"Inline policy {POLICY_NAME} added to role {ROLE_NAME}")
    print(f"\nAdd to .env:  AGENT_SESSION_TABLE={TABLE_NAME}")


def delete() -> None:
    ddb = boto3.client('dynamodb', region_name=config.AWS_REGION)
    iam = boto3.client('iam')
    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME)
        print(f"Deleted inline policy {POLICY_NAME} from {ROLE_NAME}")
    except iam.exceptions.NoSuchEntityException:
        pass
    try:
        ddb.delete_table(TableName=TABLE_NAME)
        print(f"Deleting table {TABLE_NAME}")
    except ddb.exceptions.ResourceNotFoundException:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Agent sessions table for conversation memory')
    parser.add_argument('--delete', action='store_true', help='remove the table and the role permission')
    args = parser.parse_args()
    delete() if args.delete else create()
