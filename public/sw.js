const VERSION='web-v31.5';
const CACHE=`minjaz-shell-${VERSION}`;
const SHELL=['/','/manifest.webmanifest','/icon.svg','/minjaz-files-demo-v302.js','/minjaz-work-center-v31.css','/minjaz-work-center-v31.js','/minjaz-push-v312.js','/minjaz-admin-provider-v315.js'];

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
    data:{url:payload.url||'/#notifications'}
  };
  event.waitUntil(self.registration.showNotification(title,options));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=(event.notification.data&&event.notification.data.url)||'/#notifications';
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
