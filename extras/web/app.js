// NovaMart Support web page.
// Sign-in uses the Cognito hosted login with the authorization code flow and PKCE
// (public client, no secret). The ID token is sent to the local server, which
// forwards the message to the AgentCore web runtime with the token as a Bearer
// header; the runtime checks the token before the agents run.

const cfg = window.NOVAMART_CONFIG;
const store = window.sessionStorage;

const $ = (id) => document.getElementById(id);

function base64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomString(length) {
  return base64url(crypto.getRandomValues(new Uint8Array(length)));
}

function tokenClaims(token) {
  const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(atob(payload));
}

async function signIn() {
  const verifier = randomString(48);
  const challenge = base64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  const state = randomString(16);
  store.setItem('pkce_verifier', verifier);
  store.setItem('oauth_state', state);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    scope: 'openid email profile',
    code_challenge_method: 'S256',
    code_challenge: challenge,
    state,
  });
  window.location.assign(`${cfg.cognitoDomain}/oauth2/authorize?${params}`);
}

async function finishSignIn(code, state) {
  if (state !== store.getItem('oauth_state')) throw new Error('Sign-in state did not match, please try again.');
  const response = await fetch(`${cfg.cognitoDomain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: cfg.clientId,
      code,
      redirect_uri: cfg.redirectUri,
      code_verifier: store.getItem('pkce_verifier'),
    }),
  });
  if (!response.ok) throw new Error(`Sign-in failed (${response.status})`);
  const tokens = await response.json();
  store.setItem('id_token', tokens.id_token);
  store.removeItem('pkce_verifier');
  store.removeItem('oauth_state');
  window.history.replaceState({}, '', cfg.redirectUri);
}

function signOut() {
  store.clear();
  const params = new URLSearchParams({ client_id: cfg.clientId, logout_uri: cfg.redirectUri });
  window.location.assign(`${cfg.cognitoDomain}/logout?${params}`);
}

function currentToken() {
  const token = store.getItem('id_token');
  if (!token) return null;
  if (tokenClaims(token).exp * 1000 < Date.now()) {
    store.removeItem('id_token');
    return null;
  }
  return token;
}

function chatSessionId() {
  let id = store.getItem('chat_session');
  if (!id) {
    id = Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, '0')).join('');
    store.setItem('chat_session', id);
  }
  return id;
}

function addMessage(text, kind) {
  const div = document.createElement('div');
  div.className = `msg ${kind}`;
  // Agent replies use **bold**; everything else is plain text
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  div.innerHTML = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  $('messages').appendChild(div);
  $('messages').scrollTop = $('messages').scrollHeight;
  return div;
}

async function send(event) {
  event.preventDefault();
  const token = currentToken();
  if (!token) return showSignedOut();
  const message = $('input').value.trim();
  if (!message) return;
  $('input').value = '';
  addMessage(message, 'mine');
  const pending = addMessage('NovaMart is looking into it...', 'theirs pending');
  $('composer').querySelector('button').disabled = true;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message, session_id: chatSessionId() }),
    });
    const body = await response.json();
    pending.remove();
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    addMessage(body.reply, 'theirs');
  } catch (error) {
    pending.remove();
    addMessage(error.message, 'theirs error');
  } finally {
    $('composer').querySelector('button').disabled = false;
    $('input').focus();
  }
}

function showSignedOut() {
  $('signed-out').hidden = false;
  $('chat').hidden = true;
  $('sign-in').hidden = false;
  $('sign-out').hidden = true;
  $('who').textContent = '';
}

function showChat(token) {
  const claims = tokenClaims(token);
  $('signed-out').hidden = true;
  $('chat').hidden = false;
  $('sign-in').hidden = true;
  $('sign-out').hidden = false;
  $('who').textContent = `${claims.email || claims['cognito:username']} · ${claims['custom:customer_id'] || 'no customer id'}`;
  $('input').focus();
}

async function start() {
  $('sign-in').addEventListener('click', signIn);
  $('sign-out').addEventListener('click', signOut);
  $('composer').addEventListener('submit', send);

  const params = new URLSearchParams(window.location.search);
  if (params.get('code')) {
    try {
      await finishSignIn(params.get('code'), params.get('state'));
    } catch (error) {
      showSignedOut();
      $('who').textContent = error.message;
      return;
    }
  }
  const token = currentToken();
  token ? showChat(token) : showSignedOut();
}

start();
