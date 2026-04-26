const params = new URLSearchParams(location.search);
const fileId = parseInt(params.get('file_id'));

let state = null;         // current file state from API
let speedDial = {};       // slot -> playlist object
let allPlaylists = [];
let selectedPlaylistId = null;
let isActioning = false;

async function init() {
  if (!fileId) { window.location.href = '/'; return; }
  try {
    const [file, playlists] = await Promise.all([
      apiFetch(`/api/files/${fileId}`),
      apiFetch('/api/playlists/'),
    ]);
    allPlaylists = playlists;
    buildSpeedDial(playlists);
    populatePlaylistSelect(playlists);
    applyState(file);
  } catch (e) {
    showToast('Failed to load', 'warn');
  }
}

function buildSpeedDial(playlists) {
  speedDial = {};
  playlists.forEach(p => { if (p.speed_dial_slot) speedDial[p.speed_dial_slot] = p; });
  renderSpeedDial();
}

function renderSpeedDial() {
  const grid = document.getElementById('speed-dial-grid');
  const section = document.getElementById('speed-dial-section');
  const slots = Object.keys(speedDial).sort();
  if (!slots.length) { section.style.display = 'none'; return; }
  section.style.display = '';
  grid.innerHTML = slots.map(slot => {
    const p = speedDial[slot];
    return `<div class="speed-dial-btn" id="sd-${slot}" onclick="addToSpeedDial(${slot})">
      <span class="speed-dial-key">${slot}</span>
      <span class="speed-dial-name">${escHtml(p.name)}</span>
    </div>`;
  }).join('');
}

function populatePlaylistSelect(playlists) {
  const sel = document.getElementById('playlist-select');
  sel.innerHTML = '<option value="">— Select playlist —</option>' +
    playlists.map(p => `<option value="${p.id}">${escHtml(p.name)}</option>`).join('');

  // Restore last used
  const last = localStorage.getItem('ss_last_playlist');
  if (last && playlists.find(p => p.id === parseInt(last))) {
    sel.value = last;
    selectedPlaylistId = parseInt(last);
  }

  sel.onchange = () => {
    selectedPlaylistId = sel.value ? parseInt(sel.value) : null;
    if (sel.value) localStorage.setItem('ss_last_playlist', sel.value);
  };
}

function applyState(file) {
  state = file;
  document.getElementById('file-name-label').textContent = file.name;

  if (file.is_complete) {
    showCompleteScreen();
    return;
  }

  showSortScreen();
  renderSong(file.current_song);
  updateProgress(file);
}

function renderSong(song) {
  if (!song) return;
  const { artist, title } = parseSongDisplay(song);
  document.getElementById('song-artist').textContent = artist;
  document.getElementById('song-title').textContent = title;
}

function updateProgress(file) {
  const processed = file.songs_added + file.current_index;
  const display = Math.min(processed + 1, file.total_count);
  document.getElementById('progress-text').textContent = `Song ${display} of ${file.total_count}`;
  document.getElementById('progress-fill').style.width = file.progress_pct + '%';
  document.getElementById('added-count').textContent = `${file.songs_added} added`;
}

function showSortScreen() {
  document.getElementById('sort-screen').style.display = '';
  document.getElementById('complete-screen').style.display = 'none';
}

function showCompleteScreen() {
  document.getElementById('sort-screen').style.display = 'none';
  const cs = document.getElementById('complete-screen');
  cs.style.display = '';
  const rem = state.remaining_count;
  document.getElementById('complete-remaining').textContent =
    rem > 0 ? `${rem} song${rem !== 1 ? 's' : ''} were skipped.` : 'All songs were added or skipped.';
  document.getElementById('complete-sort-remaining').style.display = rem > 0 ? '' : 'none';
}

async function doAction(action, playlistId) {
  if (isActioning || !state || state.is_complete) return;

  if (action === 'add' && !playlistId) {
    showToast('Select a playlist first', 'warn');
    return;
  }

  isActioning = true;
  flashCard();

  try {
    const resp = await apiFetch('/api/sort/action', {
      method: 'POST',
      body: JSON.stringify({ source_file_id: fileId, action, playlist_id: playlistId || null }),
    });

    if (resp.duplicate) {
      showToast('Already in playlist — skipped duplicate', 'warn');
    }

    applyState({ ...resp, name: state.name });

    if (!resp.is_complete && resp.next_song) {
      renderSong(resp.next_song);
      updateProgress(resp);
    }
  } catch (e) {
    showToast(e.message, 'warn');
  } finally {
    isActioning = false;
  }
}

async function doUndo() {
  if (isActioning) return;
  isActioning = true;
  try {
    const resp = await apiFetch('/api/sort/undo', {
      method: 'POST',
      body: JSON.stringify({ source_file_id: fileId }),
    });
    showSortScreen();
    renderSong(resp.next_song);
    state = { ...resp, name: state.name };
    updateProgress(resp);
    showToast('Undone', 'success', 1200);
  } catch (e) {
    showToast('Nothing to undo', 'warn', 1200);
  } finally {
    isActioning = false;
  }
}

async function doRestart() {
  if (!confirm('Restart from the beginning of remaining songs?')) return;
  const resp = await apiFetch(`/api/files/${fileId}/restart`, { method: 'POST' });
  applyState(resp);
  showSortScreen();
  renderSong(resp.current_song);
}

async function addToSpeedDial(slot) {
  const playlist = speedDial[slot];
  if (!playlist) return;
  await doAction('add', playlist.id);

  // Pulse the button
  const btn = document.getElementById(`sd-${slot}`);
  if (btn) {
    btn.classList.add('pulse');
    setTimeout(() => btn.classList.remove('pulse'), 400);
  }
}

function flashCard() {
  const card = document.getElementById('song-card');
  card.classList.add('flash');
  setTimeout(() => card.classList.remove('flash'), 100);
}

document.addEventListener('keydown', async e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

  const key = e.key;
  const isMeta = e.metaKey || e.ctrlKey;

  if (key === 'ArrowRight') { e.preventDefault(); doAction('add', selectedPlaylistId); }
  else if (key === 'ArrowLeft') { e.preventDefault(); doAction('skip', null); }
  else if (isMeta && key === 'z') { e.preventDefault(); doUndo(); }
  else if (key >= '1' && key <= '9') {
    const slot = parseInt(key);
    if (speedDial[slot]) { e.preventDefault(); addToSpeedDial(slot); }
  }
});

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

init();
