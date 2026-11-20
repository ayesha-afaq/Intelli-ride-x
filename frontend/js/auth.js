// ── AUTH LOGIC ─────────────────────────────────────────────────────────────
const DEFAULT_PAGE = { Student: 'student-book', Administrator: 'admin-stations' };

async function login(email, password) {
  const data = await post('/auth/login', { email, password });
  const user = { user_id: data.user_id, role: data.role, name: email };
  localStorage.setItem('token', data.access_token);
  localStorage.setItem('user', JSON.stringify(user));
  setState({ token: data.access_token, user, loading: false, error: null });
  setPage(DEFAULT_PAGE[data.role] || 'student-book');
}

async function register(d) {
  await post('/auth/register', d);
  setState({ loading: false, success: 'Registered. You can log in now.', data: { authTab: 'login' } });
}

function logout() {
  localStorage.clear();
  setState({ token: null, user: null, page: 'student-book', data: {}, modal: null, loading: false, error: null, success: null });
}

// ── AUTH VIEWS ─────────────────────────────────────────────────────────────
function renderAuth() {
  const tab = state.data.authTab || 'login';
  return `
  <div class="auth-wrap"><div class="auth-card">
    <div class="auth-logo">&gt; intelliride-x</div>
    <div class="auth-sub">Campus bicycle sharing</div>
    <div class="auth-tabs">
      <div class="auth-tab ${tab === 'login' ? 'active' : ''}" data-tab="login">Login</div>
      <div class="auth-tab ${tab === 'register' ? 'active' : ''}" data-tab="register">Register</div>
    </div>
    ${state.error ? `<div class="alert alert-error">${esc(state.error)}</div>` : ''}
    ${state.success ? `<div class="alert alert-success">${esc(state.success)}</div>` : ''}
    ${tab === 'login' ? `
    <form data-form="login">
      <div class="field"><label>Email</label><input type="email" name="email" required autocomplete="email"></div>
      <div class="field"><label>Password</label><input type="password" name="password" required autocomplete="current-password"></div>
      <button class="btn btn-primary btn-full mt-3" type="submit" ${state.loading ? 'disabled' : ''}>${state.loading ? 'Logging in...' : 'Login'}</button>
    </form>` : `
    <form data-form="register">
      <div class="field"><label>Full name</label><input name="full_name" required autocomplete="name"></div>
      <div class="field"><label>Email</label><input type="email" name="email" required autocomplete="email"></div>
      <div class="field"><label>CNIC</label><input name="cnic" placeholder="42101-1234567-1" required pattern="\\d{5}-\\d{7}-\\d" title="Format: 42101-1234567-1"></div>
      <div class="field"><label>Password <span class="text-muted">(6+ characters with a letter, a number and a symbol)</span></label>
        <input type="password" name="password" required minlength="6" autocomplete="new-password"></div>
      <button class="btn btn-primary btn-full mt-3" type="submit" ${state.loading ? 'disabled' : ''}>${state.loading ? 'Registering...' : 'Create account'}</button>
    </form>`}
  </div></div>`;
}
