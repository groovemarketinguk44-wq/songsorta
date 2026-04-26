let appleDevToken = null;
let appleMusicInstance = null;
let appleImportType = 'playlist';
let appleSelectedPlaylist = null;

async function initConnect() {
  // Show status banners from OAuth redirects
  const params = new URLSearchParams(location.search);
  if (params.get('spotify') === 'connected') {
    showBanner('Spotify connected successfully!', 'success');
    history.replaceState({}, '', '/connect');
  }
  const err = params.get('error');
  if (err) {
    showBanner(err === 'spotify_denied' ? 'Spotify connection was cancelled.' : 'Connection failed.', 'warn');
    history.replaceState({}, '', '/connect');
  }

  await Promise.all([loadSpotifyStatus(), loadAppleStatus()]);
}

function showBanner(msg, type) {
  const el = document.getElementById('status-banner');
  el.innerHTML = `<div class="toast show" style="position:relative;transform:none;margin-bottom:16px;display:inline-block">${msg}</div>`;
  el.querySelector('.toast').className = `toast ${type} show`;
}

// ── Spotify ─────────────────────────────────────────────────────────────────

async function loadSpotifyStatus() {
  try {
    const data = await apiFetch('/api/spotify/status');
    const statusEl = document.getElementById('spotify-status-text');
    const actionsEl = document.getElementById('spotify-actions');

    if (!data.configured) {
      statusEl.textContent = 'Not configured';
      document.getElementById('setup-notice').style.display = '';
      return;
    }
    if (data.connected) {
      statusEl.innerHTML = `<span style="color:var(--accent)">✓ Connected</span>${data.display_name ? ` as <strong>${escHtml(data.display_name)}</strong>` : ''}`;
      actionsEl.innerHTML = `<button class="btn btn-ghost btn-sm" onclick="disconnectSpotify()">Disconnect</button>`;
    } else {
      statusEl.textContent = 'Not connected';
      actionsEl.innerHTML = `<a href="${escHtml(data.connect_url)}" class="btn btn-secondary btn-sm">Connect Spotify</a>`;
    }
  } catch (e) {
    document.getElementById('spotify-status-text').textContent = 'Error loading status';
  }
}

async function disconnectSpotify() {
  if (!confirm('Disconnect Spotify?')) return;
  await apiFetch('/api/spotify/disconnect', { method: 'DELETE' });
  loadSpotifyStatus();
}

// ── Apple Music ──────────────────────────────────────────────────────────────

async function loadAppleStatus() {
  try {
    const data = await apiFetch('/api/apple/status');
    const statusEl = document.getElementById('apple-status-text');
    const actionsEl = document.getElementById('apple-actions');
    const noteEl = document.getElementById('apple-note');

    if (!data.configured) {
      statusEl.textContent = 'Not configured';
      document.getElementById('setup-notice').style.display = '';
      return;
    }

    noteEl.style.display = '';
    const authorized = localStorage.getItem('ss_apple_token');
    if (authorized) {
      statusEl.innerHTML = '<span style="color:var(--accent)">✓ Authorized</span>';
      actionsEl.innerHTML = `
        <button class="btn btn-ghost btn-sm" onclick="openAppleImport()">Import playlist</button>
        <button class="btn btn-ghost btn-sm" onclick="disconnectApple()" style="margin-left:6px">Disconnect</button>`;
    } else {
      statusEl.textContent = 'Not authorized';
      actionsEl.innerHTML = `<button class="btn btn-secondary btn-sm" onclick="authorizeApple()">Authorize Apple Music</button>`;
    }
  } catch (e) {
    document.getElementById('apple-status-text').textContent = 'Error loading status';
  }
}

async function getAppleInstance() {
  if (appleMusicInstance) return appleMusicInstance;
  if (!appleDevToken) {
    const data = await apiFetch('/api/apple/developer-token');
    appleDevToken = data.token;
  }
  await waitForMusicKit();
  await MusicKit.configure({ developerToken: appleDevToken, app: { name: 'SongSorta', build: '1.0.0' } });
  appleMusicInstance = MusicKit.getInstance();
  return appleMusicInstance;
}

function waitForMusicKit() {
  return new Promise((resolve) => {
    if (window.MusicKit) { resolve(); return; }
    document.addEventListener('musickitloaded', resolve, { once: true });
    setTimeout(resolve, 5000); // fallback
  });
}

async function authorizeApple() {
  try {
    const music = await getAppleInstance();
    const userToken = await music.authorize();
    localStorage.setItem('ss_apple_token', userToken);
    loadAppleStatus();
    showBanner('Apple Music authorized!', 'success');
  } catch (e) {
    showBanner('Apple Music authorization failed: ' + e.message, 'warn');
  }
}

function disconnectApple() {
  localStorage.removeItem('ss_apple_token');
  if (appleMusicInstance) {
    try { appleMusicInstance.unauthorize(); } catch (_) {}
    appleMusicInstance = null;
  }
  loadAppleStatus();
}

async function openAppleImport() {
  document.getElementById('apple-import-modal').classList.add('open');
  document.getElementById('apple-pl-list').innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const music = await getAppleInstance();
    const userToken = localStorage.getItem('ss_apple_token');
    if (!userToken) { await authorizeApple(); return; }

    const resp = await fetch('https://api.music.apple.com/v1/me/library/playlists?limit=100', {
      headers: { 'Authorization': `Bearer ${appleDevToken}`, 'Music-User-Token': userToken }
    });
    const data = await resp.json();
    const playlists = data.data || [];

    if (!playlists.length) {
      document.getElementById('apple-pl-list').innerHTML = '<div class="empty-state">No playlists found</div>';
      return;
    }

    document.getElementById('apple-pl-list').innerHTML = playlists.map(p => `
      <div class="file-item" style="cursor:pointer" onclick="selectApplePlaylist('${escHtml(p.id)}', '${escHtml(p.attributes?.name || 'Playlist')}', this)">
        <div class="file-info">
          <div class="file-name">${escHtml(p.attributes?.name || 'Untitled')}</div>
          <div class="file-meta">${p.attributes?.trackCount ?? ''} tracks</div>
        </div>
        <div style="color:var(--text-dim);font-size:1.2rem">›</div>
      </div>`).join('');
  } catch (e) {
    document.getElementById('apple-pl-list').innerHTML = `<div class="empty-state" style="color:var(--danger)">${e.message}</div>`;
  }
}

function setAppleImportType(type) {
  appleImportType = type;
  document.getElementById('apple-as-playlist').className = 'login-tab' + (type === 'playlist' ? ' active' : '');
  document.getElementById('apple-as-songlist').className = 'login-tab' + (type === 'songlist' ? ' active' : '');
  if (appleSelectedPlaylist) doAppleImport(appleSelectedPlaylist.id, appleSelectedPlaylist.name);
}

async function selectApplePlaylist(id, name, el) {
  appleSelectedPlaylist = { id, name };
  document.querySelectorAll('#apple-pl-list .file-item').forEach(i => i.style.borderColor = '');
  if (el) el.style.borderColor = 'var(--accent)';
  await doAppleImport(id, name);
}

async function doAppleImport(playlistId, playlistName) {
  const userToken = localStorage.getItem('ss_apple_token');
  if (!userToken) return;

  document.getElementById('apple-import-modal').classList.remove('open');
  showBanner(`Importing "${playlistName}"…`, '');

  try {
    const songs = [];
    let url = `https://api.music.apple.com/v1/me/library/playlists/${playlistId}/tracks?limit=100`;
    while (url) {
      const resp = await fetch(url, {
        headers: { 'Authorization': `Bearer ${appleDevToken}`, 'Music-User-Token': userToken }
      });
      const data = await resp.json();
      (data.data || []).forEach(t => {
        const artist = t.attributes?.artistName || 'Unknown';
        const title = t.attributes?.name || 'Unknown';
        songs.push(`${artist} - ${title}`);
      });
      url = data.next ? `https://api.music.apple.com${data.next}` : null;
    }

    const result = await apiFetch('/api/apple/import', {
      method: 'POST',
      body: JSON.stringify({ name: playlistName, songs, import_as: appleImportType }),
    });

    showBanner(`Imported ${result.count} songs as ${result.type === 'songlist' ? 'song list' : 'playlist'} "${result.name}"`, 'success');
    setTimeout(() => { window.location.href = '/'; }, 1500);
  } catch (e) {
    showBanner('Import failed: ' + e.message, 'warn');
  }
}

// Apple Music export (called from playlist page)
async function exportToAppleMusic(songs, playlistName) {
  try {
    const music = await getAppleInstance();
    let userToken = localStorage.getItem('ss_apple_token');
    if (!userToken) {
      userToken = await music.authorize();
      localStorage.setItem('ss_apple_token', userToken);
    }

    showBanner(`Exporting "${playlistName}" to Apple Music…`, '');

    // Create playlist
    const createResp = await fetch('https://api.music.apple.com/v1/me/library/playlists', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${appleDevToken}`,
        'Music-User-Token': userToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ attributes: { name: playlistName } }),
    });
    const created = await createResp.json();
    const newPlaylistId = created.data?.[0]?.id;
    if (!newPlaylistId) throw new Error('Failed to create playlist');

    // Search and collect catalog IDs
    const storefront = 'gb'; // could be made user-configurable
    const tracks = [];
    const notFound = [];
    for (const song of songs) {
      const searchResp = await fetch(
        `https://api.music.apple.com/v1/catalog/${storefront}/search?term=${encodeURIComponent(song)}&types=songs&limit=1`,
        { headers: { 'Authorization': `Bearer ${appleDevToken}`, 'Music-User-Token': userToken } }
      );
      const searchData = await searchResp.json();
      const results = searchData.results?.songs?.data;
      if (results?.length) {
        tracks.push({ id: results[0].id, type: 'songs' });
      } else {
        notFound.push(song);
      }
    }

    // Add tracks in batches of 25 (Apple limit)
    for (let i = 0; i < tracks.length; i += 25) {
      await fetch(`https://api.music.apple.com/v1/me/library/playlists/${newPlaylistId}/tracks`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${appleDevToken}`,
          'Music-User-Token': userToken,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ data: tracks.slice(i, i + 25) }),
      });
    }

    return { added: tracks.length, not_found: notFound };
  } catch (e) {
    throw e;
  }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Close modals on overlay click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('open');
});
