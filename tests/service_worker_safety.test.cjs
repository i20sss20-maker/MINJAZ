'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const src=fs.readFileSync('public/sw.js','utf8');
const origin='https://minjaz-app-prod-production.up.railway.app';
const handlers={};
const entries=new Map(),writes=[];
let network=async()=>new Response('OK',{status:200});
let notification,opened;
const mockCache={
  addAll:async paths=>{for(const path of paths)entries.set(path,new Response('asset'))},
  put:async(key,response)=>{
    const id=typeof key==='string'?key:new URL(key.url).pathname;
    writes.push(id);entries.set(id,response.clone());
  }
};
const caches={
  open:async name=>{assert.equal(name,'minjaz-shell-web-v31.7');return mockCache},
  match:async key=>{const id=typeof key==='string'?key:new URL(key.url).pathname;return entries.get(id)?.clone()},
  keys:async()=>['minjaz-shell-web-v31.7'],
  delete:async()=>true
};
const self={
  location:{origin},
  addEventListener:(name,fn)=>handlers[name]=fn,
  registration:{showNotification:async(title,opts)=>{notification={title,opts}}},
  skipWaiting:async()=>{},clients:{claim:async()=>{}}
};
const clients={matchAll:async()=>[],openWindow:async target=>{opened=target}};
vm.runInNewContext(src,{self,clients,caches,fetch:(...args)=>network(...args),Request,Response,URL,Set});
async function dispatch(type,event){
  const waits=[];let result;
  handlers[type]({...event,respondWith:p=>result=Promise.resolve(p),waitUntil:p=>waits.push(Promise.resolve(p))});
  const response=result?await result:null;
  await Promise.all(waits);
  return response;
}
const navigation=(path,mode='navigate')=>({request:{url:origin+path,method:'GET',mode}});
async function main(){
  entries.set('/',new Response('original shell',{status:200,headers:{'content-type':'text/html'}}));
  network=async()=>new Response('private policy page',{status:200,headers:{'content-type':'text/html'}});
  assert.equal((await dispatch('fetch',navigation('/privacy'))).status,200);
  assert.equal(await entries.get('/').text(),'original shell');
  assert.ok(!writes.includes('/'));

  network=async()=>new Response('not found',{status:404,headers:{'content-type':'text/html'}});
  await dispatch('fetch',navigation('/'));
  assert.equal(await entries.get('/').text(),'original shell');

  network=async()=>new Response('query variant',{status:200,headers:{'content-type':'text/html'}});
  await dispatch('fetch',navigation('/?app_lang=en'));
  assert.equal(await entries.get('/').text(),'original shell');

  network=async()=>new Response('confidential',{status:200,headers:{'content-type':'text/html','cache-control':'private, no-store'}});
  await dispatch('fetch',navigation('/'));
  assert.equal(await entries.get('/').text(),'original shell');

  network=async()=>new Response('updated shell',{status:200,headers:{'content-type':'text/html'}});
  await dispatch('fetch',navigation('/'));
  assert.equal(await entries.get('/').text(),'updated shell');

  network=async()=>{throw Error('offline')};
  assert.equal(await (await dispatch('fetch',navigation('/'))).text(),'updated shell');
  assert.equal((await dispatch('fetch',navigation('/privacy'))).status,503);

  let handled=false;
  handlers.fetch({request:navigation('/api/v1/me').request,respondWith:()=>handled=true,waitUntil:()=>{}});
  assert.equal(handled,false);
  handlers.fetch({request:navigation('/download/document','cors').request,respondWith:()=>handled=true,waitUntil:()=>{}});
  assert.equal(handled,false);

  await dispatch('push',{data:{json:()=>({title:'Test',url:'https://evil.example/phishing'})}});
  assert.equal(notification.opts.data.url,'/#notifications');
  await dispatch('notificationclick',{notification:{data:{url:'javascript:alert(1)'},close(){}}});
  assert.equal(opened,'/#notifications');
  await dispatch('notificationclick',{notification:{data:{url:'/#orders'},close(){}}});
  assert.equal(opened,'/#orders');
  await dispatch('notificationclick',{notification:{data:{url:'//evil.example/steal'},close(){}}});
  assert.equal(opened,'/#notifications');
  console.log('MINJAZ_PWA_CACHE_AND_NOTIFICATION_SAFETY_OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
