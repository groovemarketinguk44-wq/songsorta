const API_BASE = '';

function getToken() {
  return localStorage.getItem('ss_token');
}

function setAuth(data) {
  localStorage.setItem('ss_token', data.token);
  localStorage.setItem('ss_user', JSON.stringify({ id: data.user_id, username: data.username }));
}

function clearAuth() {
  localStorage.removeItem('ss_token');
  localStorage.removeItem('ss_user');
}

function getUser() {
  const u = localStorage.getItem('ss_user');
  return u ? JSON.parse(u) : null;
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body instanceof FormData) delete headers['Content-Type'];

  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) {
    clearAuth();
    window.location.href = '/login';
    return;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || 'Request failed');
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

function parseSongDisplay(song) {
  const normalized = song.replace('–', '-').replace('—', '-');
  const idx = normalized.indexOf(' - ');
  if (idx !== -1) {
    return { artist: normalized.slice(0, idx).trim(), title: normalized.slice(idx + 3).trim() };
  }
  const dashIdx = normalized.indexOf('-');
  if (dashIdx !== -1) {
    return { artist: normalized.slice(0, dashIdx).trim(), title: normalized.slice(dashIdx + 1).trim() };
  }
  return { artist: song, title: '' };
}

function showToast(msg, type = '', duration = 2500) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.className = `toast ${type}`; }, duration);
}
