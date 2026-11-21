// ── AUTH LOGIC ─────────────────────────────────────────────────────────────
const DEFAULT_PAGE = { Student: 'student-book', Administrator: 'admin-stations' };

async function login(email, password) {
  const data = await post('/auth/login', { email, password });
  const user = { user_id: data.user_id, role: data.role, name: email };
  localStorage.setItem('token', data.access_token);
  localStorage.setItem('user', JSON.stringify(user));
  // Clear draft on successful login
  setState({ token: data.access_token, user, loading: false, error: null, data: { ...state.data, authDraft: {} } });
  setPage(DEFAULT_PAGE[data.role] || 'student-book');
}

async function register(d) {
  await post('/auth/register', d);
  // Clear draft on success
  setState({ loading: false, success: 'Registered. You can log in now.', data: { authTab: 'login', authDraft: {} } });
}

function logout() {
  localStorage.clear();
  setState({ token: null, user: null, page: 'student-book', data: {}, modal: null, loading: false, error: null, success: null });
}

// ── PASSWORD FIELD WITH EYE TOGGLE ────────────────────────────────────────
function pwField({ name, label = 'Password', hint = '', autocomplete = 'current-password', value = '' }) {
  const id = 'pw-' + name;
  return `
  <div class="field">
    <label for="${id}">${label}${hint ? ` <span class="text-muted">${hint}</span>` : ''}</label>
    <div class="pw-wrap">
      <input id="${id}" type="password" name="${name}" required minlength="6"
             autocomplete="${autocomplete}" value="${esc(value)}">
      <button type="button" class="pw-eye" data-pw-toggle="${id}" tabindex="-1" aria-label="Show password">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="18" height="18">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </svg>
      </button>
    </div>
  </div>`;
}

// ── AUTH VIEWS ─────────────────────────────────────────────────────────────
function renderAuth() {
  const tab   = state.data.authTab  || 'login';
  const draft = state.data.authDraft || {};
  return `
  <div class="auth-wrap"><div class="auth-card">
    <div class="auth-logo">&gt; intelliride-x</div>
    <div class="auth-sub">Campus bicycle sharing</div>
    <div class="auth-tabs">
      <div class="auth-tab ${tab === 'login'    ? 'active' : ''}" data-tab="login">Login</div>
      <div class="auth-tab ${tab === 'register' ? 'active' : ''}" data-tab="register">Register</div>
    </div>
    ${state.error   ? `<div class="alert alert-error">${esc(state.error)}</div>`     : ''}
    ${state.success ? `<div class="alert alert-success">${esc(state.success)}</div>` : ''}
    ${tab === 'login' ? `
    <form data-form="login">
      <div class="field"><label>Email</label>
        <input type="email" name="email" required autocomplete="email" value="${esc(draft.email || '')}">
      </div>
      ${pwField({ name: 'password', autocomplete: 'current-password', value: draft.password || '' })}
      <button class="btn btn-primary btn-full mt-3" type="submit" ${state.loading ? 'disabled' : ''}>${state.loading ? 'Logging in…' : 'Login'}</button>
    </form>` : `
    <form data-form="register">
      <div class="field"><label>Full name</label>
        <input name="full_name" required autocomplete="name" value="${esc(draft.full_name || '')}">
      </div>
      <div class="field"><label>Email</label>
        <input type="email" name="email" required autocomplete="email" value="${esc(draft.email || '')}">
      </div>
      <div class="field"><label>CNIC</label>
        <input name="cnic" placeholder="42101-1234567-1" required
               pattern="\\d{5}-\\d{7}-\\d" title="Format: 42101-1234567-1"
               value="${esc(draft.cnic || '')}">
      </div>
      ${pwField({ name: 'password', label: 'Password', hint: '(6+ chars · letter · number · symbol)', autocomplete: 'new-password', value: draft.password || '' })}
      <button class="btn btn-primary btn-full mt-3" type="submit" ${state.loading ? 'disabled' : ''}>${state.loading ? 'Registering…' : 'Create account'}</button>
    </form>`}
  </div></div>`;
}
