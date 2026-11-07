import assert from 'node:assert/strict';
import {PNG} from 'pngjs';
import jsQR from 'jsqr';

const base = new URL(process.argv[2]).origin;
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 25000);
const players = [];
async function post(path, body, player) {
  const response = await fetch(base + path, {method:'POST', signal:controller.signal,
    headers:{'Content-Type':'application/json', Origin:base, ...(player ? {Authorization:`Bearer ${player.reconnectToken}`} : {})}, body:JSON.stringify(body)});
  assert.ok(response.ok, `POST ${path}: ${response.status}`);
  return response.json();
}
async function events(player) {
  const response = await fetch(`${base}/api/rooms/${player.roomCode}/events?token=${player.reconnectToken}`, {signal:controller.signal});
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/event-stream/);
  const reader = response.body.getReader();
  let buffer = '';
  const decoder = new TextDecoder();
  return {async until(predicate) {
    for (;;) {
      const split = buffer.indexOf('\n\n');
      if (split >= 0) {
        const block = buffer.slice(0, split); buffer = buffer.slice(split + 2);
        const data = /^data: (.*)$/m.exec(block)?.[1];
        if (data) {const value = JSON.parse(data); if (predicate(value)) return value;}
      } else {
        const chunk = await reader.read();
        assert.ok(!chunk.done, 'SSE terminó antes de recibir el estado esperado');
        buffer += decoder.decode(chunk.value, {stream:true});
      }
    }
  }};
}
try {
  const host = await post('/api/rooms', {nickname:'Prueba QR'}); players.push(host);
  const info = await (await fetch(`${base}/api/rooms/${host.roomCode}/invite`, {signal:controller.signal})).json();
  assert.equal(info.join_url, `${base}/?room=${host.roomCode}`);
  const image = await fetch(base + info.qr_url, {signal:controller.signal});
  const png = PNG.sync.read(Buffer.from(await image.arrayBuffer()));
  assert.equal(jsQR(new Uint8ClampedArray(png.data), png.width, png.height).data, info.join_url);
  const guest = await post(`/api/rooms/${host.roomCode}/join`, {nickname:'Prueba externa'}); players.push(guest);
  const streams = await Promise.all(players.map(events));
  await Promise.all(streams.map(stream => stream.until(state => state.players?.length === 2 && state.players.every(player => player.connected))));
  await post(`/api/rooms/${host.roomCode}/start`, {}, host);
  await Promise.all(streams.map(stream => stream.until(state => state.phase === 'running')));
  await post(`/api/rooms/${host.roomCode}/input`, {seq:1, horizontal:1}, guest);
  await Promise.all(streams.map(stream => stream.until(state => state.players?.some(player => player.id === guest.playerId && player.lastInputSeq === 1))));
  console.log('HTTPS público, QR decodificado, dos jugadores, SSE, inicio e input compartido: OK');
} finally {
  for (const player of players) {
    try {await post(`/api/rooms/${player.roomCode}/leave`, {}, player);} catch {}
  }
  clearTimeout(timeout); controller.abort();
}
