const byId = id => document.getElementById(id);
export function initializeInvite() {
  const code = new URL(location.href).searchParams.get('room')?.trim().toUpperCase();
  if (code && /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}$/.test(code)) {
    byId('code').value = code;
    byId('code-field').hidden = true;
    byId('create').hidden = true;
    byId('join').textContent = `Entrar a la sala ${code}`;
    byId('entry-title').textContent = `Te invitaron a la sala ${code}`;
    byId('nickname').focus();
  }
  byId('copy-invite').addEventListener('click', async () => {
    const value = byId('invite-link').value;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(value);
      byId('invite-status').textContent = 'Enlace copiado. Compártelo con los jugadores.';
    } catch {
      byId('invite-link').focus();
      byId('invite-link').select();
      byId('invite-status').textContent = 'Selecciona y copia el enlace mostrado.';
    }
  });
  return code && /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}$/.test(code) ? code : null;
}

export async function showInvitation(code) {
  const panel = byId('invite');
  panel.hidden = false;
  byId('invite-status').textContent = 'Preparando invitación…';
  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(code)}/invite`);
    if (!response.ok) throw new Error('invite unavailable');
    const info = await response.json();
    const url = new URL(info.join_url);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('invalid invite');
    byId('invite-qr').src = `/api/rooms/${encodeURIComponent(code)}/qr.png`;
    byId('invite-qr').hidden = false;
    byId('invite-link').value = url.href;
    byId('copy-invite').disabled = false;
    byId('invite-status').textContent = info.local_only
      ? 'Este enlace solo abre en este PC. Para teléfonos abre el juego desde su dirección Wi‑Fi; para otras redes configura una dirección pública HTTPS del juego.'
      : 'Escanea el QR o comparte el enlace. La sala ya está incluida: cada persona solo escribe su apodo. La dirección debe estar accesible desde la red de los jugadores.';
  } catch {
    byId('invite-qr').hidden = true;
    byId('copy-invite').disabled = true;
    byId('invite-status').textContent = 'No se pudo preparar el QR. Puedes compartir el código de sala como alternativa.';
  }
}
