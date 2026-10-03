(function(){
  if(typeof demoApi!=='function')return;
  var baseDemoV302=demoApi;
  function arr(v){return Array.isArray(v)?v:[]}
  function attachment(a,meta){
    a=a||{};meta=meta||{};
    return {
      id:a.id||('demo-file-'+Math.random().toString(36).slice(2)),
      uploaded_by:a.uploaded_by||meta.uploaded_by||null,
      task_id:meta.task_id||a.task_id||null,
      order_id:meta.order_id||a.order_id||null,
      message_id:meta.message_id||a.message_id||null,
      delivery_id:meta.delivery_id||a.delivery_id||null,
      file_name:a.file_name||a.name||'attachment',
      file_url:a.file_url||a.url||'',
      mime_type:a.mime_type||a.type||'application/octet-stream',
      size_bytes:Number(a.size_bytes||a.size||0)||0,
      storage_mode:a.storage_mode||'demo',
      created_at:a.created_at||meta.created_at||new Date().toISOString(),
      uploaded_by_name:meta.uploaded_by_name||'',
      task_title:meta.task_title||'',
      source_type:meta.source_type||'task'
    };
  }

  demoApi=async function(path,opt={}){
    var raw=String(path||''),clean=raw.split('?')[0],method=String(opt.method||'GET').toUpperCase();

    if(clean==='/api/v1/files'&&method==='GET'){
      var d=demoLoad(),u=demoAuth(d);if(!u)return baseDemoV302(path,opt);
      var orders=arr(d.orders).filter(function(o){return Number(o.client_id)===Number(u.id)||Number(o.freelancer_id)===Number(u.id)});
      var orderById=new Map(orders.map(function(o){return [Number(o.id),o]}));
      var orderByTask=new Map;
      orders.forEach(function(o){if(!orderByTask.has(Number(o.task_id)))orderByTask.set(Number(o.task_id),o)});
      var rows=[];

      arr(d.tasks).forEach(function(task){
        var shared=Number(task.client_id)===Number(u.id)||orderByTask.has(Number(task.id));if(!shared)return;
        var order=orderByTask.get(Number(task.id))||null,owner=demoUser(d,task.client_id)||{};
        arr(task.attachments).forEach(function(a){
          rows.push(attachment(a,{uploaded_by:a.uploaded_by||task.client_id,uploaded_by_name:owner.name||'',task_id:task.id,order_id:order&&order.id,task_title:task.title||'',source_type:'task',created_at:task.created_at}));
        });
      });

      arr(d.messages).forEach(function(msg){
        var order=orderById.get(Number(msg.order_id));if(!order)return;
        var task=arr(d.tasks).find(function(x){return Number(x.id)===Number(order.task_id)})||{},sender=demoUser(d,msg.sender_id)||{};
        arr(msg.attachments).forEach(function(a){
          rows.push(attachment(a,{uploaded_by:a.uploaded_by||msg.sender_id,uploaded_by_name:sender.name||'',task_id:order.task_id,order_id:order.id,message_id:msg.id,task_title:task.title||'',source_type:'message',created_at:msg.created_at}));
        });
      });

      arr(d.deliveries).forEach(function(delivery){
        var order=orderById.get(Number(delivery.order_id));if(!order)return;
        var task=arr(d.tasks).find(function(x){return Number(x.id)===Number(order.task_id)})||{},sender=demoUser(d,delivery.freelancer_id)||{};
        arr(delivery.attachments).forEach(function(a){
          rows.push(attachment(a,{uploaded_by:a.uploaded_by||delivery.freelancer_id,uploaded_by_name:sender.name||'',task_id:order.task_id,order_id:order.id,delivery_id:delivery.id,task_title:task.title||'',source_type:'delivery',created_at:delivery.created_at}));
        });
      });

      rows.sort(function(a,b){return String(b.created_at||'').localeCompare(String(a.created_at||''))});
      return demoResp(200,{items:rows});
    }

    var res=await baseDemoV302(path,opt);
    if(!res?.r?.ok||method!=='POST')return res;

    var d=demoLoad(),u=demoAuth(d),b=demoBody(opt);if(!u)return res;
    var changed=false,m;

    if(clean==='/api/v1/tasks'&&res.j?.id&&Array.isArray(b.attachments)){
      var task=arr(d.tasks).find(function(x){return Number(x.id)===Number(res.j.id)});
      if(task){task.attachments=b.attachments.map(function(a){return Object.assign({},a,{uploaded_by:a.uploaded_by||u.id,created_at:a.created_at||new Date().toISOString()})});changed=true}
    }

    m=clean.match(/^\/api\/v1\/orders\/(\d+)\/messages$/);
    if(m&&Array.isArray(b.attachments)){
      var msgId=res.j&&res.j.id;
      var msg=arr(d.messages).find(function(x){return msgId?Number(x.id)===Number(msgId):Number(x.order_id)===Number(m[1])&&Number(x.sender_id)===Number(u.id)});
      if(msg){msg.attachments=b.attachments.map(function(a){return Object.assign({},a,{uploaded_by:a.uploaded_by||u.id,created_at:a.created_at||new Date().toISOString()})});changed=true}
    }

    m=clean.match(/^\/api\/v1\/orders\/(\d+)\/deliver$/);
    if(m&&Array.isArray(b.attachments)){
      var deliveries=arr(d.deliveries).filter(function(x){return Number(x.order_id)===Number(m[1])&&Number(x.freelancer_id)===Number(u.id)}).sort(function(a,b){return Number(b.id||0)-Number(a.id||0)});
      if(deliveries[0]){deliveries[0].attachments=b.attachments.map(function(a){return Object.assign({},a,{uploaded_by:a.uploaded_by||u.id,created_at:a.created_at||new Date().toISOString()})});changed=true}
    }

    if(changed)demoSave(d);
    return res;
  };
})();
