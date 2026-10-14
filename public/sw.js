const VERSION='web-v31.7';
const CACHE=`minjaz-shell-${VERSION}`;
const SHELL=['/','/manifest.webmanifest','/icon.svg','/minjaz-files-demo-v302.js','/minjaz-work-center-v31.css','/minjaz-work-center-v31.js','/minjaz-push-v312.js','/minjaz-admin-provider-v315.js','/minjaz-release-v316.js'];

const STATIC_SHELL=new Set(SHELL.filter(path=>path!=='/'));
const NOTIFICATION_FALLBACK='/#notifications';
function cacheable(response){
  if(!response||!response.ok||response.type==='opaque')return false;
  return !/\b(no-store|private)\b/i.test(response.headers.get('cache-control')||'');
}
function safeNotificationTarget(value){
  try{
    const u=new URL(typeof value==='string'?value:NOTIFICATION_FALLBACK,self.location.origin);
    return u.origin===self.location.origin?u.pathname+u.search+u.hash:NOTIFICATION_FALLBACK;
  }catch(_){return NOTIFICATION_FALLBACK}
}
function offlineResponse(){
  return new Response('تعذر الاتصال بالإنترنت. حاول مرة أخرى عند عودة الاتصال. / You are offline. Please try again when connected.',{
    status:503,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}
  });
}
function keepCache(event,key,response){
  const copy=response.clone();
  event.waitUntil(caches.open(CACHE).then(cache=>cache.put(key,copy)).catch(()=>{}));
}

self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    const cache=await caches.open(CACHE);
    await cache.addAll([...STATIC_SHELL]);
    // Precache only public, cacheable HTML as the offline app shell.
    try{
      const response=await fetch(new Request(new URL('/',self.location.origin).href,{credentials:'same-origin'}));
      if(cacheable(response)&&/text\/html/i.test(response.headers.get('content-type')||'')){
        await cache.put('/',response);
      }
    }catch(_){}
    await self.skipWaiting();
  })());
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('minjaz-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.startsWith('/api/')||url.pathname==='/health'||url.pathname==='/readiness')return;

  if(req.mode==='navigate'){
    event.respondWith(fetch(req).then(response=>{
      // Never let legal pages, errors, or query variants overwrite home.
      if(url.pathname==='/'&&!url.search&&cacheable(response)&&/text\/html/i.test(response.headers.get('content-type')||'')){
        keepCache(event,'/',response);
      }
      return response;
    }).catch(async()=>url.pathname==='/'?(await caches.match('/'))||offlineResponse():offlineResponse()));
    return;
  }

  // Only cache known shell assets, not arbitrary GET files or private URLs.
  if(!STATIC_SHELL.has(url.pathname)||url.search)return;
  event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(response=>{
    if(cacheable(response))keepCache(event,req,response);
    return response;
  })));
});

self.addEventListener('push',event=>{
  let payload={};
  try{payload=event.data?event.data.json():{}}catch(_){
    try{payload={body:event.data?event.data.text():''}}catch(__){payload={}}
  }
  const title=payload.title||'مِنجاز';
  const options={
    body:payload.body||'عندك تحديث جديد في مِنجاز',
    icon:'/icon.svg',
    tag:payload.tag||('minjaz-'+(payload.kind||'general')),
    renotify:true,
    data:{url:safeNotificationTarget(payload.url)}
  };
  event.waitUntil(self.registration.showNotification(title,options));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=safeNotificationTarget(event.notification.data&&event.notification.data.url);
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(async list=>{
    for(const client of list){
      try{
        const u=new URL(client.url);
        if(u.origin===self.location.origin){
          if('navigate' in client)await client.navigate(target);
          return client.focus();
        }
      }catch(_){}
    }
    return clients.openWindow?clients.openWindow(target):undefined;
  }));
});
