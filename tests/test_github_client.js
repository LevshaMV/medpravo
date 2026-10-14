const assert=require('node:assert/strict');
const {createGitHubClient}=require('../github_static/github-client.js');
async function main(){
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 const data={schema:1,sources:[{id:'a',seeds:['https://example.org/']}],settings:{enabled_sources:['a']},topics:['ОМС'],publications:[],workflow_url:'https://github.com/LevshaMV/medpravo/actions/workflows/collect.yml'};
 for(let i=0;i<55;i++)data.publications.push({url:'https://example.org/'+i,title:'Приказ об ОМС '+i,relevance:'medical',source_id:'a',source_ids:['a','b'],topics:['ОМС'],source_page:'javascript:alert(1)',download_path:'../../private.txt'});
 data.publications.push({url:'javascript:alert(1)',title:'bad'});
 const urls=[];
 const fetch=async url=>{urls.push(String(url));return {ok:true,json:async()=>structuredClone(data),blob:async()=>Buffer.from('document')};};
 let client=createGitHubClient('https://levshamv.github.io/medpravo/',fetch,storage);
 const state=await client('state');assert.equal(state.count,55);assert.equal(state.unread,55);
 let result=await client('publications?relevance=all&offset=50');assert.equal(result.publications.length,5);assert.equal(result.publications[0].source_page,null);assert.equal(result.publications[0].download_path,null);
 result=await client('publications?q=ПРИКАЗ&source=b&topic=ОМС');assert.equal(result.total,55);
 await client('review',{url:'https://example.org/0',reviewed:true});
 client=createGitHubClient('https://levshamv.github.io/medpravo/',fetch,storage);assert.equal((await client('state')).unread,54);
 assert.equal((await client('publications?unread=1')).total,54);
 await client('review',{url:'https://example.org/0',reviewed:false});assert.equal((await client('state')).unread,55);
 await assert.rejects(client.download('../../private.txt'),/не подготовлена/);
 const path='files/'+'a'.repeat(64)+'.zip';await client.download(path,'test.zip');
 assert.equal(urls.at(-1),'https://levshamv.github.io/medpravo/'+path);
 assert.ok(urls.every(u=>u.startsWith('https://levshamv.github.io/medpravo/')));
 await assert.rejects(client('settings',{}),/GitHub Actions/);
 const blocked=createGitHubClient('https://example.org/test/',fetch,{getItem:()=>null,setItem:()=>{throw Error('blocked');}});
 await blocked('state');await assert.rejects(blocked('review',{url:'https://example.org/0',reviewed:true}),/не разрешает/);
 console.log('GitHub client checks passed: filtering, paging, read flags, relative paths, unsafe links, storage failure');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
