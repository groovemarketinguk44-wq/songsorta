let allPlaylists = [];

async function loadDashboard() {
  const [files, playlists] = await Promise.all([
    apiFetch('/api/files/'),
    apiFetch('/api/playlists/'),
  ]);
  allPlaylists = playlists;
  renderFiles(files);
  renderPlaylists(playlists);
}

function renderFiles(files) {
  const container = document.getElementById('files-list');
  if (!files.length) {
    container.innerHTML = '<div class="empty-state">No song lists yet. Upload one to get started.</div>';
    return;
  }
  container.innerHTML = files.map(f => {
    const pct = f.progress_pct;
    const statusText = f.is_complete
      ? `Complete — ${f.remaining_count} song${f.remaining_count !== 1 ? 's' : ''} remaining`
      : `${f.songs_added} added · ${f.remaining_count} remaining`;
    const actions = f.is_complete
      ? `${f.remaining_count > 0
          ? `<button class="btn btn-primary btn-sm" onclick="goSort(${f.id})">Sort ${f.remaining_count} Remaining</button>`
          : '<span style="color:var(--text-dim);font-size:0.8rem">All sorted</span>'}`
      : `<button class="btn btn-primary btn-sm" onclick="goSort(${f.id})">Resume</button>`;
    return `
      <div class="file-item">
        <div class="file-info">
          <div class="file-name">${escHtml(f.name)}</div>
          <div class="file-meta">${statusText}</div>
          <div class="progress-wrap" style="margin-top:6px">
            <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
          </div>
        </div>
        <div class="file-actions">
          ${actions}
          <button class="btn btn-ghost btn-xs" onclick="openBulkToPlaylist(${f.id},'${escHtml(f.name)}')">Bulk</button>
          <button class="btn btn-ghost btn-xs" onclick="exportRemaining(${f.id}, '${escHtml(f.name)}')">Export</button>
          <button class="btn btn-ghost btn-xs" onclick="deleteFile(${f.id})" style="color:var(--danger)">✕</button>
        </div>
      </div>`;
  }).join('');
}

function renderPlaylists(playlists) {
  const container = document.getElementById('playlists-list');
  if (!playlists.length) {
    container.innerHTML = '<div class="empty-state">No playlists yet.</div>';
    return;
  }
  container.innerHTML = playlists.map(p => {
    const slotBadge = p.speed_dial_slot
      ? `<span class="speed-dial-badge">${p.speed_dial_slot}</span>` : '';
    return `
      <div class="playlist-item" draggable="true" data-id="${p.id}">
        <div class="playlist-drag-handle" title="Drag to reorder">⠿</div>
        <div class="playlist-info">
          <div class="playlist-name" style="display:flex;align-items:center;gap:8px">
            ${slotBadge}${escHtml(p.name)}
          </div>
          <div class="playlist-meta">${p.song_count} song${p.song_count !== 1 ? 's' : ''}</div>
        </div>
        <div class="playlist-actions">
          <button class="btn btn-ghost btn-xs" onclick="openSpeedDialPicker(${p.id})">⚡</button>
          <button class="btn btn-ghost btn-xs" onclick="sortPlaylist(${p.id})">↺ Sort</button>
          <button class="btn btn-ghost btn-xs" onclick="window.location='/playlist?id=${p.id}'">View</button>
          <button class="btn btn-ghost btn-xs" onclick="exportPlaylist(${p.id}, '${escHtml(p.name)}')">↓ txt</button>
          ${window._spotifyConnected ? `<button class="btn btn-ghost btn-xs" onclick="exportToSpotify(${p.id},'${escHtml(p.name)}')" style="color:#1DB954">→ Spotify</button>` : ''}
          ${window._appleConfigured ? `<button class="btn btn-ghost btn-xs" onclick="exportToAppleMusicFromDashboard(${p.id},'${escHtml(p.name)}')" style="color:#fc3c44">→ Apple</button>` : ''}
          <button class="btn btn-ghost btn-xs" onclick="deletePlaylist(${p.id})" style="color:var(--danger)">✕</button>
        </div>
      </div>`;
  }).join('');
  initPlaylistDrag();
}

let plDragSrc = null;

function initPlaylistDrag() {
  const items = document.querySelectorAll('#playlists-list .playlist-item');
  items.forEach(item => {
    item.addEventListener('dragstart', e => {
      plDragSrc = item;
      e.dataTransfer.effectAllowed = 'move';
      setTimeout(() => item.classList.add('dragging'), 0);
    });
    item.addEventListener('dragend', () => {
      item.classList.remove('dragging');
      document.querySelectorAll('#playlists-list .playlist-item').forEach(i => i.classList.remove('drag-over'));
      plDragSrc = null;
    });
    item.addEventListener('dragover', e => {
      e.preventDefault();
      if (item === plDragSrc) return;
      document.querySelectorAll('#playlists-list .playlist-item').forEach(i => i.classList.remove('drag-over'));
      item.classList.add('drag-over');
    });
    item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
    item.addEventListener('drop', e => {
      e.preventDefault();
      if (!plDragSrc || item === plDragSrc) return;
      item.classList.remove('drag-over');

      const container = document.getElementById('playlists-list');
      const allItems = [...container.querySelectorAll('.playlist-item')];
      const srcIdx = allItems.indexOf(plDragSrc);
      const tgtIdx = allItems.indexOf(item);

      if (srcIdx < tgtIdx) item.after(plDragSrc);
      else item.before(plDragSrc);

      const newOrder = [...container.querySelectorAll('.playlist-item')].map(i => parseInt(i.dataset.id));
      savePlaylistOrder(newOrder);
    });
  });
}

async function savePlaylistOrder(ids) {
  await apiFetch('/api/playlists/reorder', {
    method: 'PUT',
    body: JSON.stringify(ids),
  });
}

function goSort(fileId) {
  window.location.href = `/sort?file_id=${fileId}`;
}

async function deleteFile(id) {
  if (!confirm('Delete this song list?')) return;
  await apiFetch(`/api/files/${id}`, { method: 'DELETE' });
  loadDashboard();
}

async function deletePlaylist(id) {
  if (!confirm('Delete this playlist?')) return;
  await apiFetch(`/api/playlists/${id}`, { method: 'DELETE' });
  loadDashboard();
}

async function sortPlaylist(id) {
  try {
    const sf = await apiFetch(`/api/playlists/${id}/sort`, { method: 'POST' });
    window.location.href = `/sort?file_id=${sf.id}`;
  } catch (e) {
    showToast(e.message, 'warn');
  }
}

function exportRemaining(id, name) {
  const token = getToken();
  window.open(`/api/files/${id}/export?token=${token}`, '_blank');
}

function exportPlaylist(id, name) {
  const token = getToken();
  window.open(`/api/playlists/${id}/export?token=${token}`, '_blank');
}

// Speed dial picker modal
let speedDialTargetId = null;

function openSpeedDialPicker(playlistId) {
  speedDialTargetId = playlistId;
  const pl = allPlaylists.find(p => p.id === playlistId);
  document.getElementById('speed-dial-playlist-name').textContent = pl ? pl.name : '';

  // Build slot buttons
  const taken = {};
  allPlaylists.forEach(p => { if (p.speed_dial_slot) taken[p.speed_dial_slot] = p.name; });
  const current = pl ? pl.speed_dial_slot : null;

  const wrap = document.getElementById('speed-dial-slots');
  wrap.innerHTML = '';
  for (let i = 1; i <= 9; i++) {
    const btn = document.createElement('button');
    btn.className = 'slot-btn' + (current === i ? ' active' : '') + (taken[i] && taken[i] !== pl?.name ? ' taken' : '');
    btn.textContent = i;
    btn.title = taken[i] && taken[i] !== pl?.name ? `Taken by ${taken[i]}` : '';
    btn.onclick = () => assignSlot(i);
    wrap.appendChild(btn);
  }
  // Clear button
  if (current) {
    const clearBtn = document.createElement('button');
    clearBtn.className = 'btn btn-ghost btn-xs';
    clearBtn.textContent = 'Clear';
    clearBtn.style.marginLeft = '8px';
    clearBtn.onclick = () => assignSlot(0);
    wrap.appendChild(clearBtn);
  }

  document.getElementById('speed-dial-modal').classList.add('open');
}

async function assignSlot(slot) {
  try {
    await apiFetch(`/api/playlists/${speedDialTargetId}/speed-dial?slot=${slot}`, { method: 'PUT' });
    document.getElementById('speed-dial-modal').classList.remove('open');
    loadDashboard();
  } catch (e) {
    showToast(e.message, 'warn');
  }
}

// Upload modal
let currentUploadType = 'songlist';

function setUploadType(type) {
  currentUploadType = type;
  document.getElementById('type-songlist').className = 'login-tab' + (type === 'songlist' ? ' active' : '');
  document.getElementById('type-playlist').className = 'login-tab' + (type === 'playlist' ? ' active' : '');
  document.getElementById('upload-type-hint').textContent = type === 'songlist'
    ? 'For sorting — songs will be sorted one by one into playlists'
    : 'Import directly as a playlist — no sorting needed';
}

function autoFillName(input) {
  if (!input.files[0]) return;
  const filename = input.files[0].name.replace(/\.(txt|docx)$/i, '');
  const nameField = document.getElementById('upload-name');
  if (!nameField.value) nameField.value = filename;
}

function openUploadModal() {
  document.getElementById('upload-modal').classList.add('open');
  document.getElementById('upload-error').textContent = '';
  document.getElementById('upload-file').value = '';
  document.getElementById('upload-name').value = '';
  setUploadType('songlist');
}

async function doUpload() {
  const file = document.getElementById('upload-file').files[0];
  const name = document.getElementById('upload-name').value.trim();
  document.getElementById('upload-error').textContent = '';

  if (!file) { document.getElementById('upload-error').textContent = 'Please select a file.'; return; }
  if (!name) { document.getElementById('upload-error').textContent = 'Please enter a name.'; return; }

  const fd = new FormData();
  fd.append('file', file);
  fd.append('name', name);

  try {
    if (currentUploadType === 'playlist') {
      const pl = await apiFetch('/api/playlists/upload', { method: 'POST', body: fd });
      document.getElementById('upload-modal').classList.remove('open');
      showToast(`Playlist imported: ${pl.song_count} songs`, 'success');
    } else {
      const sf = await apiFetch('/api/files/upload', { method: 'POST', body: fd });
      document.getElementById('upload-modal').classList.remove('open');
      showToast(`Uploaded ${sf.total_count} songs`, 'success');
    }
    loadDashboard();
  } catch (e) {
    document.getElementById('upload-error').textContent = e.message;
  }
}

// Create playlist modal
function openCreatePlaylist() {
  document.getElementById('create-playlist-modal').classList.add('open');
  document.getElementById('new-playlist-name').value = '';
  document.getElementById('create-playlist-error').textContent = '';
}

async function doCreatePlaylist() {
  const name = document.getElementById('new-playlist-name').value.trim();
  if (!name) { document.getElementById('create-playlist-error').textContent = 'Enter a name.'; return; }
  try {
    await apiFetch('/api/playlists/', { method: 'POST', body: JSON.stringify({ name }) });
    document.getElementById('create-playlist-modal').classList.remove('open');
    loadDashboard();
  } catch (e) {
    document.getElementById('create-playlist-error').textContent = e.message;
  }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Close modals on overlay click
document.querySelectorAll('.modal-overlay').forEach(el => {
  el.addEventListener('click', e => { if (e.target === el) el.classList.remove('open'); });
});

// Enter key for modals
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
});

// ── Music service connections ─────────────────────────────────────────────

window._spotifyConnected = false;
window._appleConfigured = false;

async function checkMusicConnections() {
  try {
    const [sp, ap] = await Promise.all([
      apiFetch('/api/spotify/status').catch(() => null),
      apiFetch('/api/apple/status').catch(() => null),
    ]);
    window._spotifyConnected = sp?.connected || false;
    window._appleConfigured = ap?.configured || false;

    if (window._spotifyConnected) {
      document.getElementById('btn-import-spotify').style.display = '';
    }
    if (window._appleConfigured) {
      document.getElementById('btn-import-apple').style.display = '';
    }
  } catch (_) {}
}

// ── Spotify import ────────────────────────────────────────────────────────

let spotifyImportType = 'songlist';

function setSpotifyImportType(type) {
  spotifyImportType = type;
  document.getElementById('sp-as-songlist').className = 'login-tab' + (type === 'songlist' ? ' active' : '');
  document.getElementById('sp-as-playlist').className = 'login-tab' + (type === 'playlist' ? ' active' : '');
}

async function openSpotifyImport() {
  document.getElementById('spotify-import-modal').classList.add('open');
  document.getElementById('spotify-pl-list').innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const playlists = await apiFetch('/api/spotify/playlists');
    if (!playlists.length) {
      document.getElementById('spotify-pl-list').innerHTML = '<div class="empty-state">No playlists found</div>';
      return;
    }
    document.getElementById('spotify-pl-list').innerHTML = playlists.map(p => `
      <div class="file-item" style="cursor:pointer" onclick="doSpotifyImport('${escHtml(p.id)}','${escHtml(p.name)}')">
        <div class="file-info">
          <div class="file-name">${escHtml(p.name)}</div>
          <div class="file-meta">${p.track_count} tracks</div>
        </div>
        <div style="color:var(--text-dim);font-size:1.2rem">›</div>
      </div>`).join('');
  } catch (e) {
    document.getElementById('spotify-pl-list').innerHTML = `<div class="empty-state" style="color:var(--danger)">${e.message}<br><a href="/connect" style="color:var(--accent)">Reconnect Spotify</a></div>`;
  }
}

async function doSpotifyImport(spotifyId, name) {
  document.getElementById('spotify-import-modal').classList.remove('open');
  showToast(`Importing "${name}"…`, '');
  try {
    const result = await apiFetch(`/api/spotify/import/${spotifyId}?import_as=${spotifyImportType}&name=${encodeURIComponent(name)}`, { method: 'POST' });
    showToast(`Imported ${result.count} songs`, 'success');
    loadDashboard();
  } catch (e) {
    showToast(e.message, 'warn');
  }
}

// ── Apple Music import (delegates to connect.js) ──────────────────────────

function openAppleMusicImport() {
  if (typeof openAppleImport === 'function') {
    openAppleImport();
  } else {
    window.location.href = '/connect';
  }
}

// ── Spotify export ────────────────────────────────────────────────────────

async function exportToSpotify(playlistId, name) {
  showToast(`Exporting "${name}" to Spotify…`, '');
  try {
    const result = await apiFetch(`/api/spotify/export/${playlistId}`, { method: 'POST' });
    const msg = result.not_found.length
      ? `Added ${result.added} to Spotify (${result.not_found.length} not found)`
      : `${result.added} tracks added to Spotify`;
    showToast(msg, 'success', 4000);
    if (result.spotify_url) window.open(result.spotify_url, '_blank');
  } catch (e) {
    showToast(e.message, 'warn');
  }
}

// ── Apple Music export ────────────────────────────────────────────────────

async function exportToAppleMusicFromDashboard(playlistId, name) {
  // Need the songs — fetch playlist detail
  try {
    const pl = await apiFetch(`/api/playlists/${playlistId}`);
    if (typeof exportToAppleMusic === 'function') {
      showToast(`Exporting "${name}" to Apple Music…`, '');
      const result = await exportToAppleMusic(pl.songs, pl.name);
      const msg = result.not_found.length
        ? `Added ${result.added} to Apple Music (${result.not_found.length} not found)`
        : `${result.added} tracks added to Apple Music`;
      showToast(msg, 'success', 4000);
    } else {
      window.location.href = '/connect';
    }
  } catch (e) {
    showToast(e.message, 'warn');
  }
}

// ── Bulk add song list → playlist ─────────────────────────────────────────

let bulkSourceFileId = null;

function openBulkToPlaylist(fileId, fileName) {
  bulkSourceFileId = fileId;
  document.getElementById('bulk-file-name').textContent = fileName;

  // Populate playlist dropdown
  const sel = document.getElementById('bulk-playlist-select');
  sel.innerHTML = '<option value="">— Select playlist —</option>' +
    allPlaylists.map(p => `<option value="${p.id}">${escHtml(p.name)}</option>`).join('');
  document.getElementById('bulk-result').textContent = '';
  document.getElementById('bulk-modal').classList.add('open');
}

async function doBulkAdd() {
  const playlistId = document.getElementById('bulk-playlist-select').value;
  if (!playlistId) { showToast('Select a playlist first', 'warn'); return; }

  const resultEl = document.getElementById('bulk-result');
  resultEl.textContent = 'Adding…';
  try {
    const [{ songs }, playlist] = await Promise.all([
      apiFetch(`/api/files/${bulkSourceFileId}/remaining-songs`),
      apiFetch(`/api/playlists/${playlistId}`),
    ]);

    if (!songs.length) { resultEl.textContent = 'No remaining songs.'; return; }

    const existing = new Set(playlist.songs.map(s => s.toLowerCase().trim()));
    const toAdd = songs.filter(s => !existing.has(s.toLowerCase().trim()));
    const dupes = songs.length - toAdd.length;

    if (!toAdd.length) {
      resultEl.textContent = `All ${songs.length} songs already in that playlist.`;
      return;
    }

    await apiFetch(`/api/playlists/${playlistId}`, {
      method: 'PUT',
      body: JSON.stringify({ songs: [...playlist.songs, ...toAdd] }),
    });

    document.getElementById('bulk-modal').classList.remove('open');
    showToast(
      dupes > 0
        ? `Added ${toAdd.length} songs (${dupes} duplicates skipped)`
        : `Added ${toAdd.length} songs to playlist`,
      'success', 3500
    );
    loadDashboard();
  } catch (e) {
    resultEl.textContent = e.message;
  }
}
