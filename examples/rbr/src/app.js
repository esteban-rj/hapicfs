import http from 'node:http';
import {configuredOrigin,invitation,invitationPng} from './invites.js';
import { readFile } from 'node:fs/promises';
import { ApiError,createEngine,fail } from './engine.js';
const assets=new Map([['/invite.js',['invite.js','text/javascript; charset=utf-8']],['/',['index.html','text/html; charset=utf-8']],['/app.js',['app.js','text/javascript; charset=utf-8']],['/styles.css',['styles.css','text/css; charset=utf-8']],['/config.js',['config.js','text/javascript; charset=utf-8']]]);
export function createApp({engine=createEngine(),autoTick=true,publicOrigin=process.env.RBR_PUBLIC_URL}={}){
 const shareOrigin=configuredOrigin(publicOrigin);
 const streams=new Map();let closing=false;
 const json=(res,status,body)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(body));};
 function closeStream(s,event,body){if(event&&!s.res.destroyed)s.res.write(`event: ${event}\ndata: ${JSON.stringify(body)}\n\n`);s.res.end();if(streams.get(s.key)===s){streams.delete(s.key);engine.disconnect(s.code,s.id,s.generation);}}
 function send(s,text){if(!s.res.write(text))closeStream(s);}
 function broadcast(code){const list=[...streams.values()].filter(s=>s.code===code);if(!list.length)return;let snap;try{snap=engine.snapshot(code);}catch{return;}const text=`id: ${snap.version}\nevent: snapshot\ndata: ${JSON.stringify(snap)}\n\n`;for(const s of list)if(s.lastVersion!==snap.version){s.lastVersion=snap.version;send(s,text);}}
 const unsubscribe=engine.onChange((r,type)=>{if(type==='closed'){for(const s of [...streams.values()])if(s.code===r.code)closeStream(s,'room-closed',{reason:'expired'});}else if(type==='sessions'){for(const s of [...streams.values()])if(s.code===r.code&&(!r.players.has(s.id)||r.players.get(s.id).sessionExpired))closeStream(s,'room-closed',{reason:'expired'});}else if(type==='phase')broadcast(r.code);});
 async function bodyOf(req){if(!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type']??''))fail(415,'CONTENT_TYPE','Usa application/json.');if(Number(req.headers['content-length'])>1024)fail(413,'BODY_LIMIT','Cuerpo demasiado grande.');const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>1024)fail(413,'BODY_LIMIT','Cuerpo demasiado grande.');chunks.push(chunk);}try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{fail(400,'BAD_JSON','JSON inválido.');}}
 const server=http.createServer(async(req,res)=>{try{
  const url=new URL(req.url,'http://local.invalid'),path=url.pathname;
  if(path.startsWith('/api/'))res.setHeader('Cache-Control','no-store');
  if(req.method==='POST'&&req.headers.origin&&req.headers.origin!==`http://${req.headers.host}`&&req.headers.origin!==shareOrigin)fail(403,'BAD_ORIGIN','Origen no permitido.');
  if(assets.has(path)){if(req.method!=='GET')fail(405,'METHOD','Método no permitido.');const [file,mime]=assets.get(path);res.writeHead(200,{'Content-Type':mime,'X-Content-Type-Options':'nosniff','Cache-Control':'no-cache','Content-Security-Policy':"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"});res.end(await readFile(new URL(`../public/${file}`,import.meta.url)));return;}
  if(path==='/api/health'){if(req.method!=='GET')fail(405,'METHOD','Método no permitido.');json(res,200,{ok:true});return;}
  if(path==='/api/rooms'){if(req.method!=='POST')fail(405,'METHOD','Método no permitido.');json(res,201,engine.create(await bodyOf(req)));return;}
  const inviteMatch=path.match(/^\/api\/rooms\/([^/]+)\/(invite|qr\.png)$/);
  if(inviteMatch){
   if(req.method!=='GET')fail(405,'METHOD','Método no permitido.');
   const snapshot=engine.snapshot(inviteMatch[1]);
   const info=invitation(snapshot.roomCode,shareOrigin||`http://${req.headers.host}`);
   if(inviteMatch[2]==='invite'){json(res,200,info);return;}
   const png=await invitationPng(info.join_url);
   res.writeHead(200,{'Content-Type':'image/png','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(png);return;
  }
  const match=path.match(/^\/api\/rooms\/([^/]+)\/(join|events|start|input|leave)$/);if(!match)fail(404,'NOT_FOUND','Ruta inexistente.');const [,code,action]=match;
  if(req.method!==(action==='events'?'GET':'POST'))fail(405,'METHOD','Método no permitido.');
  // Missing room takes precedence over authentication and request validation.
  engine.snapshot(code);
  if(action==='events'){
   const token=url.searchParams.get('token');const {r,p,generation}=engine.connect(code,token),key=`${r.code}:${p.id}`,previous=streams.get(key);
   if(previous)closeStream(previous,'session-replaced',{reason:'new_connection'});
   res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-cache, no-transform','Connection':'keep-alive','X-Accel-Buffering':'no'});res.flushHeaders();res.write('retry: 1000\n\n');const s={code:r.code,id:p.id,generation,key,res,lastVersion:-1};streams.set(key,s);res.on('close',()=>{if(streams.get(key)===s){streams.delete(key);engine.disconnect(r.code,p.id,generation);}});broadcast(r.code);return;
  }
  const body=await bodyOf(req);if(action==='join'){json(res,201,engine.join(code,body));return;}
  const token=/^Bearer (.+)$/.exec(req.headers.authorization??'')?.[1];const result=engine[action](code,token,body);json(res,action==='input'&&result.accepted?202:200,result);
 }catch(e){if(!res.headersSent)json(res,e instanceof ApiError?e.status:500,{error:{code:e instanceof ApiError?e.code:'INTERNAL',message:e instanceof ApiError?e.message:'Error interno.'}});else res.end();}});
 const timers=[];if(autoTick)timers.push(setInterval(()=>engine.step(),50));timers.push(setInterval(()=>{for(const code of new Set([...streams.values()].map(s=>s.code)))broadcast(code);},100));timers.push(setInterval(()=>{for(const s of [...streams.values()])send(s,': heartbeat\n\n');},10000));
 async function close(){if(closing)return;closing=true;timers.forEach(clearInterval);unsubscribe();for(const s of [...streams.values()])closeStream(s);server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
 return {server,engine,broadcast,close};
}
