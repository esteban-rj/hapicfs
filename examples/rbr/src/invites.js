import QRCode from 'qrcode';
import {normalizeCode} from './engine.js';

export function configuredOrigin(value) {
  if (!value) return null;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash)
    throw new Error('RBR_PUBLIC_URL debe ser el origen HTTP/HTTPS del juego, sin rutas ni credenciales.');
  return url.origin;
}

export function invitation(code, origin) {
  const roomCode = normalizeCode(code);
  const url = new URL('/', configuredOrigin(origin));
  url.searchParams.set('room', roomCode);
  return {room_code: roomCode, join_url: url.href,
    qr_url: `/api/rooms/${roomCode}/qr.png`,
    local_only: ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)};
}

export function invitationPng(url) {
  return QRCode.toBuffer(url, {type: 'png', width: 320, margin: 4, errorCorrectionLevel: 'M'});
}
