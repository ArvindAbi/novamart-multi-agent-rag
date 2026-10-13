"""
web_server.py
=============
Stand-out extra: serve the NovaMart web page and pass chat messages to the
Cognito-protected AgentCore web runtime.

  python extras/web_server.py        # http://localhost:8080

The page signs the customer in with Cognito and sends its ID token here. This
server forwards the message to the runtime's HTTPS endpoint with that token as a
Bearer header (no AWS credentials involved); the runtime's JWT authorizer checks
the token, so a request with a missing, expired or forged token never reaches the
agents. The customer id comes from the token's custom:customer_id claim, not from
anything typed on the page. Serving page and API from one origin avoids CORS.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config

WEB_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
HOST, PORT  = '127.0.0.1', 8080
RUNTIME_ARN = os.environ.get('WEB_RUNTIME_ARN', '')
STATIC      = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js',
               '/style.css': 'style.css', '/config.js': 'config.js'}


def _claims(token: str) -> dict:
    payload = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in STATIC:
            self.send_error(404)
            return
        self.path = '/' + STATIC[path]
        super().do_GET()

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != '/api/chat':
            self.send_error(404)
            return
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return self._json(401, {'error': 'Please sign in first.'})
        token = auth[len('Bearer '):]
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            customer_id = _claims(token).get('custom:customer_id', '')
        except (ValueError, IndexError):
            return self._json(400, {'error': 'Bad request.'})
        if not customer_id:
            return self._json(403, {'error': 'This login has no NovaMart customer id.'})

        session_id = ''.join(c for c in str(body.get('session_id', '')) if c.isalnum())[:16] or 'web'
        url = (f"https://bedrock-agentcore.{config.AWS_REGION}.amazonaws.com/runtimes/"
               f"{urllib.parse.quote(RUNTIME_ARN, safe='')}/invocations?qualifier=DEFAULT")
        request = urllib.request.Request(
            url,
            data=json.dumps({'prompt': str(body.get('message', ''))[:2000],
                             'customer_id': customer_id,
                             'session_id': session_id}).encode(),
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                # AgentCore needs >= 33 characters; one stable id per chat keeps the same runtime session
                'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': f"novamart-web-chat-{customer_id}-{session_id}".ljust(33, '0'),
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read())
            self._json(200, {'reply': result.get('result', ''), 'trace_id': result.get('trace_id')})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors='replace')[:300]
            message = ('Your sign-in was not accepted. Please sign in again.'
                       if exc.code in (401, 403) else f'The support service returned {exc.code}.')
            print(f"runtime error {exc.code}: {detail}", file=sys.stderr)
            self._json(exc.code, {'error': message})
        except Exception as exc:
            print(f"runtime call failed: {exc}", file=sys.stderr)
            self._json(502, {'error': 'The support service could not be reached.'})


if __name__ == '__main__':
    if not RUNTIME_ARN:
        sys.exit("WEB_RUNTIME_ARN is not set in .env - run extras/web_setup.py first")
    if not os.path.exists(os.path.join(WEB_DIR, 'config.js')):
        sys.exit("extras/web/config.js is missing - run extras/web_setup.py first")
    print(f"NovaMart web page on http://localhost:{PORT}  (runtime {RUNTIME_ARN.split('/')[-1]})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
