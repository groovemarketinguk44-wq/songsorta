const params = new URLSearchParams(location.search);
const playlistId = parseInt(params.get('id'));

let songs = [];
let dragSrcIndex = null;

async function init() {
  if (!playlistId) { window.location.href = '/'; return; }
  const pl = await apiFetch(`/api/playlists/${playlistId}`);
  songs = pl.songs;
  renderHeader(pl);
  renderSongs();
}

function renderHeader(pl) {
  document.getElementById('pl-name').textContent = pl.name;
  document.getElementById('pl-meta').textContent = `${pl.song_count} song${pl.song_count !== 1 ? 's' : ''}${pl.speed_dial_slot ? ` · Speed dial: ${pl.speed_dial_slot}` : ''}`;
  document.getElementById('pl-title').textContent = pl.name;
}

function renderSongs() {
  const container = document.getElementById('song-list');
  if (!songs.length) {
    container.innerHTML = '<div class="empty-state">No songs yet.</div>';
    return;
  }
  container.innerHTML = songs.map((song, i) => `
    <div class="song-row" draggable="true" data-index="${i}"
      ondragstart="dragStart(event,${i})"
      ondragover="dragOver(event,${i})"
      ondrop="dragDrop(event,${i})"
      ondragleave="dragLeave(event)"
      ondragend="dragEnd()">
      <span class="song-row-num">${i + 1}</span>
      <span class="song-row-text">${escHtml(song)}</span>
      <button class="song-row-delete" onclick="deleteSong(${i})" title="Remove">✕</button>
    </div>`).join('');

  document.getElementById('pl-meta').textContent = `${songs.length} song${songs.length !== 1 ? 's' : ''}`;
}

// Drag and drop
function dragStart(e, i) {
  dragSrcIndex = i;
  e.dataTransfer.effectAllowed = 'move';
  setTimeout(() => e.target.classList.add('dragging'), 0);
}

function dragOver(e, i) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  document.querySelectorAll('.song-row').forEach(r => r.classList.remove('drag-over'));
  e.currentTarget.classList.add('drag-over');
}

function dragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

function dragDrop(e, targetIndex) {
  e.preventDefault();
  if (dragSrcIndex === null || dragSrcIndex === targetIndex) return;
  const moved = songs.splice(dragSrcIndex, 1)[0];
  songs.splice(targetIndex, 0, moved);
  renderSongs();
  saveSongs();
}

function dragEnd() {
  document.querySelectorAll('.song-row').forEach(r => {
    r.classList.remove('dragging', 'drag-over');
  });
  dragSrcIndex = null;
}

async function deleteSong(index) {
  songs.splice(index, 1);
  renderSongs();
  await saveSongs();
}

async function saveSongs() {
  await apiFetch(`/api/playlists/${playlistId}`, {
    method: 'PUT',
    body: JSON.stringify({ songs }),
  });
}

async function renamePlaylist() {
  const name = prompt('New name:', document.getElementById('pl-name').textContent);
  if (!name || !name.trim()) return;
  const pl = await apiFetch(`/api/playlists/${playlistId}`, {
    method: 'PUT',
    body: JSON.stringify({ name: name.trim() }),
  });
  renderHeader(pl);
}

function exportPlaylist() {
  const token = getToken();
  window.open(`/api/playlists/${playlistId}/export?token=${token}`, '_blank');
}

async function sortPlaylist() {
  const sf = await apiFetch(`/api/playlists/${playlistId}/sort`, { method: 'POST' });
  window.location.href = `/sort?file_id=${sf.id}`;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

init();
