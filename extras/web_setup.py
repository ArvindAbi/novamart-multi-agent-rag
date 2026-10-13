"""
web_setup.py
============
Stand-out extra: Cognito customer login and a JWT-protected AgentCore runtime
for the NovaMart web page.

  python extras/web_setup.py            # create or update everything
  python extras/web_setup.py --delete   # remove it again

Creates
  - Cognito user pool `novamart-customers` with a custom `customer_id` attribute
    (admin-created users only), a public app client for the page (authorization
    code flow with PKCE, redirect http://localhost:8080/) and a hosted login domain
  - AgentCore runtime `udacity_agentcore_web`: same code package, role, network,
    protocol and environment as the graded runtime (read from AGENTCORE_RUNTIME_ARN),
    plus a Cognito JWT authorizer. The graded runtime keeps AWS IAM (SigV4) auth,
    so `invoke`, the tests and the AgentCore CLI keep working.
  - extras/web/config.js for the page, and WEB_RUNTIME_ARN in .env for web_server.py

The web runtime is created with the control-plane API instead of the AgentCore CLI
project in agentcore/, which the starter asks us not to change.
"""

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import boto3
import config
from agent_observability import wait_for_runtime_ready

POOL_NAME    = 'novamart-customers'
CLIENT_NAME  = 'novamart-web'
DOMAIN       = f"novamart-{config.ACCOUNT_ID}"
RUNTIME_NAME = 'udacity_agentcore_web'
REDIRECT_URI = 'http://localhost:8080/'
ENV_FILE     = os.path.join(ROOT, '.env')
CONFIG_JS    = os.path.join(ROOT, 'extras', 'web', 'config.js')


def _find_pool(idp) -> str:
    for page in idp.get_paginator('list_user_pools').paginate(MaxResults=60):
        for pool in page['UserPools']:
            if pool['Name'] == POOL_NAME:
                return pool['Id']
    return ''


def setup_cognito(idp) -> tuple[str, str]:
    pool_id = _find_pool(idp)
    if not pool_id:
        pool_id = idp.create_user_pool(
            PoolName=POOL_NAME,
            Policies={'PasswordPolicy': {'MinimumLength': 10, 'RequireUppercase': True,
                                         'RequireLowercase': True, 'RequireNumbers': True,
                                         'RequireSymbols': False}},
            AdminCreateUserConfig={'AllowAdminCreateUserOnly': True},
            UsernameConfiguration={'CaseSensitive': False},
            Schema=[{'Name': 'customer_id', 'AttributeDataType': 'String', 'Mutable': True,
                     'StringAttributeConstraints': {'MinLength': '1', 'MaxLength': '20'}}],
        )['UserPool']['Id']
        print(f"Created user pool {POOL_NAME} ({pool_id})")
    else:
        print(f"User pool {POOL_NAME} exists ({pool_id})")

    client_id = next((c['ClientId'] for c in
                      idp.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)['UserPoolClients']
                      if c['ClientName'] == CLIENT_NAME), '')
    if not client_id:
        client_id = idp.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName=CLIENT_NAME,
            GenerateSecret=False,
            AllowedOAuthFlows=['code'],
            AllowedOAuthFlowsUserPoolClient=True,
            AllowedOAuthScopes=['openid', 'email', 'profile'],
            CallbackURLs=[REDIRECT_URI],
            LogoutURLs=[REDIRECT_URI],
            SupportedIdentityProviders=['COGNITO'],
            ExplicitAuthFlows=['ALLOW_USER_SRP_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH'],
            ReadAttributes=['email', 'custom:customer_id'],
            WriteAttributes=['email'],
            PreventUserExistenceErrors='ENABLED',
            IdTokenValidity=60, AccessTokenValidity=60,
            TokenValidityUnits={'IdToken': 'minutes', 'AccessToken': 'minutes'},
        )['UserPoolClient']['ClientId']
        print(f"Created app client {CLIENT_NAME} ({client_id})")

    if not idp.describe_user_pool(UserPoolId=pool_id)['UserPool'].get('Domain'):
        idp.create_user_pool_domain(Domain=DOMAIN, UserPoolId=pool_id, ManagedLoginVersion=1)
        print(f"Created hosted login domain {DOMAIN}")
    return pool_id, client_id


def _find_runtime(ctrl) -> dict:
    for rt in ctrl.list_agent_runtimes().get('agentRuntimes', []):
        if rt['agentRuntimeName'] == RUNTIME_NAME:
            return rt
    return {}


def setup_runtime(ctrl, pool_id: str, client_id: str) -> str:
    if not config.AGENTCORE_RUNTIME_ARN:
        sys.exit("AGENTCORE_RUNTIME_ARN is not set - deploy the graded runtime first")
    graded = ctrl.get_agent_runtime(agentRuntimeId=config.AGENTCORE_RUNTIME_ARN.split('/')[-1])
    params = dict(
        agentRuntimeArtifact=graded['agentRuntimeArtifact'],
        roleArn=graded['roleArn'],
        networkConfiguration=graded['networkConfiguration'],
        protocolConfiguration=graded['protocolConfiguration'],
        environmentVariables=graded.get('environmentVariables') or {},
        authorizerConfiguration={'customJWTAuthorizer': {
            'discoveryUrl': (f"https://cognito-idp.{config.AWS_REGION}.amazonaws.com/"
                             f"{pool_id}/.well-known/openid-configuration"),
            # Cognito ID tokens carry the app client id in `aud`
            'allowedAudience': [client_id],
        }},
        description='NovaMart support agents for the web page (Cognito JWT auth)',
    )
    existing = _find_runtime(ctrl)
    if existing:
        ctrl.update_agent_runtime(agentRuntimeId=existing['agentRuntimeId'], **params)
        runtime_id, runtime_arn = existing['agentRuntimeId'], existing['agentRuntimeArn']
        print(f"Updated runtime {RUNTIME_NAME}")
    else:
        resp = ctrl.create_agent_runtime(agentRuntimeName=RUNTIME_NAME, **params)
        runtime_id, runtime_arn = resp['agentRuntimeId'], resp['agentRuntimeArn']
        print(f"Created runtime {RUNTIME_NAME}")
    print("Waiting for READY", end='', flush=True)
    time.sleep(5)
    wait_for_runtime_ready(ctrl, runtime_id)
    print(' ready.')
    return runtime_arn


def _set_env(key: str, value: str) -> None:
    text = open(ENV_FILE).read() if os.path.exists(ENV_FILE) else ''
    line = f"{key}={value}"
    if re.search(rf'^{key}=.*$', text, flags=re.M):
        text = re.sub(rf'^{key}=.*$', line, text, flags=re.M)
    else:
        text += f"\n# Stand-out extra: web page runtime (extras/web_setup.py)\n{line}\n"
    with open(ENV_FILE, 'w') as fh:
        fh.write(text)


def create() -> None:
    idp  = boto3.client('cognito-idp', region_name=config.AWS_REGION)
    ctrl = boto3.client('bedrock-agentcore-control', region_name=config.AWS_REGION)
    pool_id, client_id = setup_cognito(idp)
    runtime_arn = setup_runtime(ctrl, pool_id, client_id)

    with open(CONFIG_JS, 'w') as fh:
        fh.write('// Written by extras/web_setup.py - public values only, no secrets\n'
                 'window.NOVAMART_CONFIG = ' + json.dumps({
                     'cognitoDomain': f"https://{DOMAIN}.auth.{config.AWS_REGION}.amazoncognito.com",
                     'clientId':      client_id,
                     'redirectUri':   REDIRECT_URI,
                 }, indent=2) + ';\n')
    _set_env('WEB_RUNTIME_ARN', runtime_arn)

    print(f"\nRuntime   : {runtime_arn}")
    print(f"User pool : {pool_id}   app client: {client_id}")
    print(f"Wrote {os.path.relpath(CONFIG_JS, ROOT)} and WEB_RUNTIME_ARN in .env")
    print("\nNext: create a login user yourself (see docs/web_frontend.md), then run "
          "`python extras/web_server.py` and open http://localhost:8080")


def delete() -> None:
    idp  = boto3.client('cognito-idp', region_name=config.AWS_REGION)
    ctrl = boto3.client('bedrock-agentcore-control', region_name=config.AWS_REGION)
    runtime = _find_runtime(ctrl)
    if runtime:
        ctrl.delete_agent_runtime(agentRuntimeId=runtime['agentRuntimeId'])
        print(f"Deleting runtime {RUNTIME_NAME}")
        for wi in ctrl.list_workload_identities().get('workloadIdentities', []):
            if runtime['agentRuntimeId'] in wi['name'] or RUNTIME_NAME in wi['name']:
                ctrl.delete_workload_identity(name=wi['name'])
                print(f"Deleted workload identity {wi['name']}")
    pool_id = _find_pool(idp)
    if pool_id:
        domain = idp.describe_user_pool(UserPoolId=pool_id)['UserPool'].get('Domain')
        if domain:
            idp.delete_user_pool_domain(Domain=domain, UserPoolId=pool_id)
        idp.delete_user_pool(UserPoolId=pool_id)
        print(f"Deleted user pool {POOL_NAME}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cognito login + JWT runtime for the web page')
    parser.add_argument('--delete', action='store_true', help='remove the user pool and the web runtime')
    args = parser.parse_args()
    delete() if args.delete else create()
