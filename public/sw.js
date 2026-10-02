const VERSION='web-v15';
const CACHE=`minjaz-shell-${VERSION}`;
const SHELL=['/','/manifest.webmanifest','/icon.svg'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('minjaz-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET') return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin) return;
  if(url.pathname.startsWith('/api/')||url.pathname==='/health'||url.pathname==='/readiness') return;

  if(req.mode==='navigate'){
    event.respondWith(fetch(req).then(res=>{
      const copy=res.clone();
      caches.open(CACHE).then(cache=>cache.put('/',copy));
      return res;
    }).catch(()=>caches.match('/')));
    return;
  }

  event.respondWith(caches.match(req).then(cached=>{
    const fresh=fetch(req).then(res=>{
      if(res.ok){const copy=res.clone();caches.open(CACHE).then(cache=>cache.put(req,copy));}
      return res;
    }).catch(()=>cached);
    return cached||fresh;
  }));
});
