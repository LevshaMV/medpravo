"use strict";
let current=null,view="publications",offset=0,searchTimer,requestSerial=0;
const filters={q:"",source:"",topic:"",relevance:"profile",unread:""};
const $=id=>document.getElementById(id);
const escape=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const labels={pending:"Ещё не проверен",blocked:"Ошибка доступа",needs_adapter:"Нужна настройка",partial:"Частичный сбор",collected:"Разделы обработаны"};
const date=value=>value?new Intl.DateTimeFormat("ru-RU",{dateStyle:"medium",timeZone:"Europe/Moscow"}).format(new Date(value.length===10?value+"T00:00:00+03:00":value)):"не указана";
const api=createMedPravoClient(window.location.href,window.fetch.bind(window),window.history);
function message(text,error=false){$("message").innerHTML='<div class="alert '+(error?"error":"")+'">'+escape(text)+'</div>';}
async function refresh(){try{current=await api("state");render();}catch(e){message(e.message,true);}}
function render(){
 if(!current)return;
 const enabled=current.sources.filter(s=>current.settings.enabled_sources.includes(s.id));
 if(current.local_test){document.querySelector('.sidebar-bottom strong').textContent='Локальная проверка';document.querySelector('.sidebar-bottom small').textContent='Автоматический сбор выключен';}
 const successful=enabled.filter(s=>["collected","partial"].includes(s.status)).length;
 $("stats").innerHTML=[["Публикаций в базе",current.count],["Не просмотрено",current.unread],["Каталоги отвечают",successful+" / "+enabled.length],["Автоматическая проверка","Каждые 6 ч"]].map(([label,value])=>'<div class="stat"><div class="stat-top">'+escape(label)+'</div><strong>'+escape(value)+'</strong></div>').join("");
 if(current.local_test){$("stats").lastElementChild.querySelector('.stat-top').textContent='Локальная проверка';$("stats").lastElementChild.querySelector('strong').textContent='Вручную';}
 $("run-status").textContent=current.scanning?"Собираем документы…":!current.schedule.enabled?"Автоматический сбор выключен":current.schedule.next_check_at?"Следующая проверка: "+new Intl.DateTimeFormat("ru-RU",{dateStyle:"short",timeStyle:"short",timeZone:"Europe/Moscow"}).format(new Date(current.schedule.next_check_at))+" МСК":"Готовим первую проверку";$("scan").disabled=current.scanning;
 $("heading").textContent={publications:"Новые публикации",sources:"Источники",settings:"Настройки"}[view];
 if(view==="publications"){
  $("body").innerHTML='<div class="coverage-note">'+(current.local_test?'Локальный тест: до двух страниц и десяти новых документов на источник. Автоматическая проверка выключена. ':'')+'Дата публикации и дата обнаружения различаются. Документы первой проверки отмечены как первоначальная подборка. Предмет акта добавляется в заголовок из описания источника, если оно доступно. Темы определяются по словам, без юридической оценки.</div><div class="toolbar feed-toolbar"><div class="searchbox"><input id="search" aria-label="Поиск" placeholder="Название или номер документа" value="'+escape(filters.q)+'"></div><select id="relevance" aria-label="Подборка"><option value="profile">Для центра + проверить вручную</option><option value="medical">По темам центра</option><option value="review">Проверить вручную</option><option value="all">Все собранные документы</option><option value="other">Остальные темы</option></select><select id="topic" aria-label="Тема"><option value="">Все темы</option>'+current.topics.map(t=>'<option>'+escape(t)+'</option>').join("")+'</select><select id="source" aria-label="Источник"><option value="">Все источники</option>'+current.sources.map(s=>'<option value="'+escape(s.id)+'">'+escape(s.name)+'</option>').join("")+'</select><label class="checkbox-label"><input type="checkbox" id="unread"> Только непросмотренные</label></div><div id="list-summary" class="plain-note"></div><section class="panel" id="publication-list"><div class="empty-docs">Загрузка…</div></section><div class="button-row pagination"><button class="button ghost" id="previous">Назад</button><button class="button ghost" id="next">Далее</button></div>';
  for(const key of ["relevance","topic","source"]){$(key).value=filters[key];$(key).onchange=()=>{filters[key]=$(key).value;offset=0;loadPublications();};}
  $("unread").checked=filters.unread==="1";$("unread").onchange=()=>{filters.unread=$("unread").checked?"1":"";offset=0;loadPublications();};
  $("search").oninput=()=>{filters.q=$("search").value;offset=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadPublications,250);};
  $("previous").onclick=()=>{offset=Math.max(0,offset-50);loadPublications();};$("next").onclick=()=>{offset+=50;loadPublications();};loadPublications();
 }else if(view==="sources"){
  $("body").innerHTML='<div class="source-intro panel"><div><h2>Проверка открытых источников</h2><p>Источник в реестре ещё не означает рабочее подключение. Если раздел недоступен, отсутствие новых документов не подтверждено.</p></div></div><div class="source-grid">'+current.sources.map(s=>'<article class="panel source-card"><span class="badge '+(["partial","blocked","needs_adapter"].includes(s.status)?"amber":"neutral")+'">'+escape(labels[s.status])+'</span><h3>'+escape(s.name)+'</h3><p>'+escape(s.description)+'</p><div class="source-detail">'+escape(s.detail||"Проверка на этом сервере ещё не выполнялась")+(s.transport_note?"<p>"+escape(s.transport_note)+"</p>":"")+'</div><div class="source-card-bottom"><span class="note">'+(current.settings.enabled_sources.includes(s.id)?"Включён":"Выключен")+' · '+date(s.checked_at)+'</span><a class="text-link" href="'+escape(s.seeds[0])+'" target="_blank" rel="noopener noreferrer">Сайт ↗</a></div></article>').join("")+'</div>';
 }else{
  $("body").innerHTML='<section class="panel settings-panel"><h2>Выберите источники</h2><p class="plain-note">На сервере проверка каждые 6 часов; в локальном тесте — только кнопкой. Письма и ИИ не используются. Новые акты о внесении изменений попадают в ленту; старые файлы не сравниваются.</p><div class="checkbox-grid">'+current.sources.map(s=>'<label class="checkbox-label"><input type="checkbox" name="source" value="'+escape(s.id)+'" '+(current.settings.enabled_sources.includes(s.id)?"checked":"")+'>'+escape(s.name)+'</label>').join("")+'</div><button class="button primary" id="save">Сохранить</button></section>';
  $("save").onclick=async()=>{try{await api("settings",{enabled_sources:[...document.querySelectorAll('input[name="source"]:checked')].map(x=>x.value)});message("Источники сохранены");await refresh();}catch(e){message(e.message,true);}};
 }
}
async function loadPublications(){
 const serial=++requestSerial;
 try{
  const result=await api("publications?"+new URLSearchParams({...filters,offset:String(offset)}));
  if(serial!==requestSerial||view!=="publications")return;
  $("list-summary").textContent="Найдено: "+result.total+(result.total?" · показаны "+(offset+1)+"–"+Math.min(offset+50,result.total):"");
  $("previous").disabled=offset===0;$("next").disabled=offset+50>=result.total;
  const names=Object.fromEntries(current.sources.map(s=>[s.id,s.name]));
  $("publication-list").innerHTML=result.publications.length?result.publications.map((p,i)=>'<article class="doc-card '+(p.reviewed?"reviewed":"")+'"><div class="doc-card-content"><div class="doc-badges"><span class="badge neutral">'+escape(p.category)+'</span>'+(p.initial?'<span class="badge neutral">Первоначальная подборка</span>':'<span class="badge">Впервые найден</span>')+(p.relevance==="review"?'<span class="badge amber">Проверить тему вручную</span>':"")+p.topics.map(t=>'<span class="badge neutral">'+escape(t)+'</span>').join("")+'</div><h3 class="event-title">'+escape(p.title)+'</h3>'+(p.original_title&&p.original_title!==p.title?'<details class="original-title"><summary>Название в источнике</summary><p>'+escape(p.original_title)+'</p></details>':'')+'<p>'+escape(names[p.source_id]||p.source_id)+' · публикация: '+date(p.published_at)+' · найден: '+date(p.first_seen)+'</p><div class="button-row">'+(p.source_page?'<a class="text-link" href="'+escape(p.source_page)+'" target="_blank" rel="noopener noreferrer">Страница публикации ↗</a>':'')+(p.file_type?'<button class="button ghost" data-download="'+i+'">Скачать через кабинет ('+escape(p.file_type.toUpperCase())+')</button><a class="text-link" href="'+escape(p.url)+'" target="_blank" rel="noopener noreferrer">Файл на сайте ↗</a>':'<a class="text-link" href="'+escape(p.url)+'" target="_blank" rel="noopener noreferrer">Открыть документ ↗</a>')+'<button class="button ghost" data-review="'+i+'">'+(p.reviewed?"Вернуть в непросмотренные":"Отметить просмотренным")+'</button></div></div></article>').join(""):'<div class="empty-docs"><h3>Публикаций пока нет</h3><p>Запустите проверку или измените фильтры. Состояние подключений доступно во вкладке «Источники».</p></div>';
  document.querySelectorAll("[data-download]").forEach(b=>b.onclick=async()=>{
    const p=result.publications[Number(b.dataset.download)],label=b.textContent;
    b.disabled=true;b.textContent="Получаем файл…";message("Получаем документ от источника. Это может занять до минуты.");
    try{
      const file=await api.download("file?"+new URLSearchParams({url:p.url}));
      const address=URL.createObjectURL(file.blob),link=document.createElement("a");
      link.href=address;link.download=file.filename;link.hidden=true;document.body.appendChild(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(address),30000);
      message("Файл получен. Проверьте загрузки браузера.");
    }catch(e){message(e.message,true);}finally{b.disabled=false;b.textContent=label;}
  });
  document.querySelectorAll("[data-review]").forEach(b=>b.onclick=async()=>{const p=result.publications[Number(b.dataset.review)];b.disabled=true;try{await api("review",{url:p.url,reviewed:!p.reviewed});current=await api("state");render();}catch(e){message(e.message,true);b.disabled=false;}});
 }catch(e){if(serial===requestSerial)message(e.message,true);}
}
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{view=b.dataset.view;requestSerial++;document.querySelectorAll("[data-view]").forEach(x=>x.classList.toggle("active",x.dataset.view===view));render();});
$("scan").onclick=async()=>{try{await api("scan",{});message("Проверка запущена. Статусы источников обновятся после сбора.");await refresh();}catch(e){message(e.message,true);}};
setInterval(()=>{if(view!=="settings"&&!document.querySelector("[data-download]:disabled")&&!['INPUT','SELECT'].includes(document.activeElement?.tagName))refresh();},30000);
refresh();
