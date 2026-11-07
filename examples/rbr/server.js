import { pathToFileURL } from 'node:url';
import { createApp } from './src/app.js';
export {createApp};
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const host=process.env.HOST??'127.0.0.1',port=Number(process.env.PORT??3000);if(!Number.isInteger(port)||port<1||port>65535)throw new Error('PORT inválido');const app=createApp();app.server.listen(port,host,()=>console.log(`RBR escuchando en http://${host}:${port}`));app.server.on('error',async error=>{console.error(error.message);await app.close();process.exitCode=1;});for(const signal of ['SIGTERM','SIGINT'])process.once(signal,async()=>{await app.close();process.exitCode=0;});}
