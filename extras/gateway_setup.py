"""
gateway_setup.py
================
Stand-out extra: deploy the three Lambda tool functions that the optional
AgentCore Gateway step (deploy_agentcore_gateway, deploy Step 6) registers as
MCP targets.

  python extras/gateway_setup.py            # create or update role + functions
  python extras/gateway_setup.py --delete   # remove them

Then add the printed ORDERS_FUNCTION / POLICY_FUNCTION / CUSTOMERS_FUNCTION lines
to .env and run the gateway step (python src/agent_orchestrator.py deploy, or
python extras/gateway_client.py --deploy).

The gateway calls the functions with the stack's AgentCore role, which has no
Lambda permission of its own, so each function gets a resource policy allowing
that role to invoke it.
"""

import argparse
import io
import json
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import boto3
import config

HERE      = os.path.dirname(os.path.abspath(__file__))
ROLE_NAME = 'novamart-gateway-lambda-role'

FUNCTIONS = {
    # env var in .env : (function name, source file)
    'ORDERS_FUNCTION':    ('novamart-orders-api',    'orders_api.py'),
    'POLICY_FUNCTION':    ('novamart-policy-api',    'policy_api.py'),
    'CUSTOMERS_FUNCTION': ('novamart-customers-api', 'customers_api.py'),
}


def _role(iam) -> str:
    """Create (or reuse) the Lambda execution role and return its ARN."""
    account = config.ACCOUNT_ID
    region  = config.AWS_REGION
    try:
        arn = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps({
                'Version': '2012-10-17',
                'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'lambda.amazonaws.com'},
                               'Action': 'sts:AssumeRole'}],
            }),
            Description='NovaMart gateway tool Lambdas (orders, policy, customers)',
        )['Role']['Arn']
        print(f"Created role {ROLE_NAME}")
        fresh = True
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=ROLE_NAME)['Role']['Arn']
        fresh = False

    iam.attach_role_policy(RoleName=ROLE_NAME,
                           PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')
    table_arn = f"arn:aws:dynamodb:{region}:{account}:table"
    kb_arn    = f"arn:aws:bedrock:{region}:{account}:knowledge-base"
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName='novamart-gateway-tools',
        PolicyDocument=json.dumps({
            'Version': '2012-10-17',
            'Statement': [
                {'Effect': 'Allow', 'Action': ['dynamodb:GetItem', 'dynamodb:Scan'],
                 'Resource': [f"{table_arn}/{config.ORDERS_TABLE}",
                              f"{table_arn}/{config.CUSTOMERS_TABLE}"]},
                {'Effect': 'Allow', 'Action': ['bedrock:Retrieve'],
                 'Resource': [f"{kb_arn}/{config.RETURNS_KB_ID}",
                              f"{kb_arn}/{config.SHIPPING_KB_ID}",
                              f"{kb_arn}/{config.WARRANTY_KB_ID}"]},
            ],
        }),
    )
    if fresh:
        print("Waiting for the new role to be usable by Lambda...")
        time.sleep(12)
    return arn


def _zip(source_file: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(os.path.join(HERE, 'gateway', source_file), arcname=source_file)
    return buffer.getvalue()


def create() -> None:
    iam = boto3.client('iam')
    lam = boto3.client('lambda', region_name=config.AWS_REGION)
    role_arn = _role(iam)
    environment = {'Variables': {
        'ORDERS_TABLE':    config.ORDERS_TABLE,
        'CUSTOMERS_TABLE': config.CUSTOMERS_TABLE,
        'RETURNS_KB_ID':   config.RETURNS_KB_ID,
        'SHIPPING_KB_ID':  config.SHIPPING_KB_ID,
        'WARRANTY_KB_ID':  config.WARRANTY_KB_ID,
    }}

    for env_key, (name, source) in FUNCTIONS.items():
        handler = f"{source[:-3]}.handler"
        code = _zip(source)
        try:
            lam.create_function(FunctionName=name, Runtime='python3.12', Role=role_arn,
                                Handler=handler, Code={'ZipFile': code}, Timeout=30,
                                MemorySize=256, Environment=environment,
                                Description=f"NovaMart gateway tool ({source})")
            print(f"Created function {name}")
        except lam.exceptions.ResourceConflictException:
            lam.update_function_code(FunctionName=name, ZipFile=code)
            lam.get_waiter('function_updated_v2').wait(FunctionName=name)
            lam.update_function_configuration(FunctionName=name, Environment=environment,
                                              Handler=handler, Role=role_arn)
            print(f"Updated function {name}")
        lam.get_waiter('function_active_v2').wait(FunctionName=name)

        try:
            lam.add_permission(FunctionName=name, StatementId='agentcore-gateway-invoke',
                               Action='lambda:InvokeFunction',
                               Principal=config.AGENTCORE_ROLE_ARN)
        except lam.exceptions.ResourceConflictException:
            pass

    print("\nAdd to .env:")
    for env_key, (name, _) in FUNCTIONS.items():
        print(f"  {env_key}={name}")


def delete() -> None:
    iam = boto3.client('iam')
    lam = boto3.client('lambda', region_name=config.AWS_REGION)
    for name, _ in FUNCTIONS.values():
        try:
            lam.delete_function(FunctionName=name)
            print(f"Deleted function {name}")
        except lam.exceptions.ResourceNotFoundException:
            pass
    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName='novamart-gateway-tools')
        iam.detach_role_policy(RoleName=ROLE_NAME,
                               PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"Deleted role {ROLE_NAME}")
    except iam.exceptions.NoSuchEntityException:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gateway tool Lambdas')
    parser.add_argument('--delete', action='store_true', help='remove the functions and their role')
    args = parser.parse_args()
    delete() if args.delete else create()
