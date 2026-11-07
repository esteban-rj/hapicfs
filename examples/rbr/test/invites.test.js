import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {PNG} from 'pngjs';
import jsQR from 'jsqr';
import {createApp} from '../src/app.js';
import {configuredOrigin, invitation} from '../src/invites.js';

test('configuración pública rechaza rutas, protocolos y credenciales', () => {
  for (const value of ['ftp://game.test', 'https://user:secret@game.test', 'https://game.test/path', 'https://game.test/?token=secret']) {
    assert.throws(() => configuredOrigin(value));
  }
  assert.equal(invitation('ABC234', 'http://127.0.0.1:3000').local_only, true);
});

test('QR decodificable abre la sala pública sin compartir la sesión del anfitrión', async t => {
  const app = createApp({autoTick:false, publicOrigin:'https://juego.example'});
  app.server.listen(0, '127.0.0.1');
  await once(app.server, 'listening');
  t.after(() => app.close());
  const base = `http://127.0.0.1:${app.server.address().port}`;
  const post = (path, origin, nickname) => fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json', Origin:origin}, body:JSON.stringify({nickname})});
  const created = await post('/api/rooms', 'https://juego.example', 'Ana');
  assert.equal(created.status, 201);
  const host = await created.json();
  const info = await (await fetch(`${base}/api/rooms/${host.roomCode}/invite`)).json();
  assert.equal(info.join_url, `https://juego.example/?room=${host.roomCode}`);
  assert.equal(info.local_only, false);
  const response = await fetch(base + info.qr_url);
  assert.equal(response.headers.get('content-type'), 'image/png');
  const png = PNG.sync.read(Buffer.from(await response.arrayBuffer()));
  const decoded = jsQR(new Uint8ClampedArray(png.data), png.width, png.height);
  assert.equal(decoded.data, info.join_url);
  assert.ok(!decoded.data.includes(host.reconnectToken));
  const guest = await post(`/api/rooms/${new URL(decoded.data).searchParams.get('room')}/join`, 'https://juego.example', 'Beto');
  assert.equal(guest.status, 201);
  assert.equal((await guest.json()).roomCode, host.roomCode);
  assert.equal((await post('/api/rooms', 'https://evil.example', 'Intruso')).status, 403);
  assert.equal((await fetch(`${base}/api/rooms/ZZZZZZ/qr.png`)).status, 404);
});
