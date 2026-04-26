const params = new URLSearchParams(location.search);
const fileId = parseInt(params.get('file_id'));

let state = null;
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
    renderPlaylistCards(playlists);
    const last = localStorage.getItem('ss_last_playlist');
    if (last && playlists.find(p => p.id === parseInt(last))) {
      selectedPlaylistId = parseInt(last);
      highlightCard(selectedPlaylistId);
    }
    applyState(file);
  } catch (e) {
    showToast('Failed to load', 'warn');
  }
}

// ── playlist cards ────────────────────────────────────────────────────────────

function renderPlaylistCards(playlists) {
  const grid = document.getElementById('pl-card-grid');
  grid.innerHTML = '';
  playlists.forEach((p, idx) => {
    const card = document.createElement('div');
    card.className = 'pl-card';
    card.dataset.id = p.id;
    card.dataset.pos = idx + 1;
    card.draggable = true;

    if (idx < 9) {
      const key = document.createElement('span');
      key.className = 'pl-card-key';
      key.textContent = idx + 1;
      card.appendChild(key);
    }

    const name = document.createElement('span');
    name.className = 'pl-card-name';
    name.textContent = p.name;
    card.appendChild(name);

    card.addEventListener('click', () => {
      selectedPlaylistId = p.id;
      localStorage.setItem('ss_last_playlist', p.id);
      highlightCard(p.id);
      doAction('add', p.id);
    });

    grid.appendChild(card);
  });
  initCardDrag();
}

function highlightCard(playlistId) {
  document.querySelectorAll('#pl-card-grid .pl-card').forEach(c => {
    c.classList.toggle('selected', parseInt(c.dataset.id) === playlistId);
  });
}

function pulseCard(playlistId) {
  const card = document.querySelector(`#pl-card-grid .pl-card[data-id="${playlistId}"]`);
  if (!card) return;
  card.classList.add('pulse');
  setTimeout(() => card.classList.remove('pulse'), 350);
}

// ── drag-and-drop reorder ─────────────────────────────────────────────────────

let cardDragSrc = null;

function initCardDrag() {
  document.querySelectorAll('#pl-card-grid .pl-card').forEach(card => {
    card.addEventListener('dragstart', e => {
      cardDragSrc = card;
      e.dataTransfer.effectAllowed = 'move';
      setTimeout(() => card.classList.add('dragging'), 0);
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      document.querySelectorAll('#pl-card-grid .pl-card').forEach(c => c.classList.remove('drag-over'));
      cardDragSrc = null;
      renumberCards();
      saveCardOrder();
    });
    card.addEventListener('dragover', e => {
      e.preventDefault();
      if (card === cardDragSrc) return;
      document.querySelectorAll('#pl-card-grid .pl-card').forEach(c => c.classList.remove('drag-over'));
      card.classList.add('drag-over');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
    card.addEventListener('drop', e => {
      e.preventDefault();
      if (!cardDragSrc || card === cardDragSrc) return;
      card.classList.remove('drag-over');
      const grid = document.getElementById('pl-card-grid');
      const all = [...grid.querySelectorAll('.pl-card')];
      if (all.indexOf(cardDragSrc) < all.indexOf(card)) card.after(cardDragSrc);
      else card.before(cardDragSrc);
    });
  });
}

function renumberCards() {
  document.querySelectorAll('#pl-card-grid .pl-card').forEach((card, idx) => {
    card.dataset.pos = idx + 1;
    let keyEl = card.querySelector('.pl-card-key');
    if (idx < 9) {
      if (!keyEl) {
        keyEl = document.createElement('span');
        keyEl.className = 'pl-card-key';
        card.prepend(keyEl);
      }
      keyEl.textContent = idx + 1;
    } else if (keyEl) {
      keyEl.remove();
    }
  });
}

async function saveCardOrder() {
  const ids = [...document.querySelectorAll('#pl-card-grid .pl-card')].map(c => parseInt(c.dataset.id));
  try {
    await apiFetch('/api/playlists/reorder', { method: 'PUT', body: JSON.stringify(ids) });
  } catch (_) {}
}

// ── state / progress ──────────────────────────────────────────────────────────

function applyState(file) {
  state = file;
  document.getElementById('file-name-label').textContent = file.name;
  if (file.is_complete) { showCompleteScreen(); return; }
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
  document.getElementById('complete-screen').style.display = '';
  const rem = state.remaining_count;
  document.getElementById('complete-remaining').textContent =
    rem > 0 ? `${rem} song${rem !== 1 ? 's' : ''} were skipped.` : 'All songs were added or skipped.';
  document.getElementById('complete-sort-remaining').style.display = rem > 0 ? '' : 'none';
}

// ── actions ───────────────────────────────────────────────────────────────────

async function doAction(action, playlistId) {
  if (isActioning || !state || state.is_complete) return;
  if (action === 'add' && !playlistId) {
    showToast('Click a playlist card or press 1–9', 'warn');
    return;
  }

  isActioning = true;
  flashCard();

  try {
    const resp = await apiFetch('/api/sort/action', {
      method: 'POST',
      body: JSON.stringify({ source_file_id: fileId, action, playlist_id: playlistId || null }),
    });

    if (resp.duplicate) showToast('Already in playlist — skipped duplicate', 'warn');
    if (action === 'add' && playlistId) pulseCard(playlistId);

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

// ── keyboard ──────────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  const isMeta = e.metaKey || e.ctrlKey;
  if (e.key === 'ArrowRight') { e.preventDefault(); doAction('add', selectedPlaylistId); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); doAction('skip', null); }
  else if (isMeta && e.key === 'z') { e.preventDefault(); doUndo(); }
  else if (e.key >= '1' && e.key <= '9') {
    const idx = parseInt(e.key) - 1;
    const cards = [...document.querySelectorAll('#pl-card-grid .pl-card')];
    if (idx < cards.length) {
      e.preventDefault();
      const playlistId = parseInt(cards[idx].dataset.id);
      selectedPlaylistId = playlistId;
      localStorage.setItem('ss_last_playlist', playlistId);
      highlightCard(playlistId);
      doAction('add', playlistId);
    }
  }
});

function flashCard() {
  const card = document.getElementById('song-card');
  card.classList.add('flash');
  setTimeout(() => card.classList.remove('flash'), 100);
}

init();
