"use strict";
function createGitHubClient(href,fetchImpl,storage){
 const base=new URL('./',href),key='medpravo-reviewed:'+base.pathname;
 let snapshot=null,read={};
 try{const saved=JSON.parse(storage.getItem(key)||'{}');if(saved&&typeof saved==='object'&&!Array.isArray(saved))read=saved;}catch{}
 const safeURL=value=>{try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}};
 const safePath=value=>/^files\/[0-9a-f]{64}\.(pdf|zip|rar|7z|doc|docx|xls|xlsx|rtf)$/.test(value||'');
 async function load(){
  const response=await fetchImpl(new URL('data.json',base),{cache:'no-store'});
  if(!response.ok)throw Error('Не удалось загрузить ленту: '+response.status);
  const data=await response.json();
  if(data.schema!==1||!Array.isArray(data.publications)||!Array.isArray(data.sources))throw Error('Некорректный формат ленты');
  data.publications=data.publications.filter(p=>safeURL(p.url)).map(p=>({...p,source_page:safeURL(p.source_page)?p.source_page:null,download_path:safePath(p.download_path)?p.download_path:null}));
  data.sources=data.sources.map(s=>({...s,seeds:s.seeds.filter(safeURL)})).filter(s=>s.seeds.length);
  data.workflow_url=/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/actions\/workflows\/collect\.yml$/.test(data.workflow_url||'')?data.workflow_url:null;
  snapshot=data;return data;
 }
 const flagged=p=>Boolean(read[p.url]);
 const api=async(path,body)=>{
  if(path==='state'){
   const data=await load();return {...data,count:data.publications.length,unread:data.publications.filter(p=>!flagged(p)&&['medical','review'].includes(p.relevance)).length};
  }
  if(!snapshot)await load();
  if(path==='review'){
   if(!snapshot.publications.some(p=>p.url===body.url)||typeof body.reviewed!=='boolean')throw Error('Документ не найден');
   const next={...read};if(body.reviewed)next[body.url]=true;else delete next[body.url];
   try{storage.setItem(key,JSON.stringify(next));}catch{throw Error('Браузер не разрешает сохранять отметки просмотра');}
   read=next;return {saved:true};
  }
  if(path.startsWith('publications?')){
   const f=new URLSearchParams(path.split('?')[1]),q=(f.get('q')||'').toLocaleLowerCase('ru-RU');
   let list=snapshot.publications.filter(p=>{
    const relevance=f.get('relevance')||'profile';
    return (relevance==='all'||(relevance==='profile'?['medical','review'].includes(p.relevance):p.relevance===relevance))&&
      (!q||p.title.toLocaleLowerCase('ru-RU').includes(q))&&
      (!f.get('source')||(p.source_ids||[p.source_id]).includes(f.get('source')))&&
      (!f.get('topic')||p.topics.includes(f.get('topic')))&&(!f.get('unread')||!flagged(p));
   });
   const offset=Math.max(0,Number.parseInt(f.get('offset')||'0',10)||0);
   return {publications:list.slice(offset,offset+50).map(p=>({...p,reviewed:flagged(p)})),total:list.length,offset,limit:50};
  }
  throw Error('Это действие доступно через GitHub Actions');
 };
 api.download=async(path,filename)=>{
  if(!safePath(path))throw Error('Копия документа не подготовлена');
  const response=await fetchImpl(new URL(path,base));
  if(!response.ok)throw Error('Копия временно недоступна. Откройте файл в источнике.');
  return {blob:await response.blob(),filename:filename||'document'};
 };
 return api;
}
if(typeof module!=='undefined')module.exports={createGitHubClient};
