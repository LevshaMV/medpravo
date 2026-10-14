"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync(require("node:path").join(__dirname,"../static/api-client.js"), "utf8");
vm.runInThisContext(code);

(async () => {
  const requests = [], cleanAddresses = [];
  const transport = async (address, options) => {
    const parsed = new URL(address);
    assert.equal(parsed.username, ""); assert.equal(parsed.password, "");
    requests.push({address, options});
    return {ok:true, json:async()=>({ok:true})};
  };
  const client = createMedPravoClient("http://owner:dummy%40password@127.0.0.1:8098/", transport,
    {replaceState:(_state,_title,address)=>cleanAddresses.push(address)});
  assert.deepEqual(await client("state"), {ok:true});
  await client("scan", {});
  await client("publications?source=tfoms&offset=50");
  await client("settings", {enabled_sources:["tfoms"]});
  await client("review", {url:"https://example.gov/doc",reviewed:true});
  assert.deepEqual(cleanAddresses, ["http://127.0.0.1:8098/"]);
  assert.equal(requests[0].options.headers.Authorization, "Basic "+Buffer.from("owner:dummy@password").toString("base64"));
  assert.equal(requests[1].options.method, "POST");
  assert.equal(requests[1].options.body, "{}");
  assert.equal(requests[2].address, "http://127.0.0.1:8098/api/publications?source=tfoms&offset=50");
  assert.equal(requests[4].options.headers["X-MedPravo-Request"], "1");
  assert.equal(requests[0].options.credentials, "same-origin");
  const ordinary = createMedPravoClient("https://cabinet.example/",transport);
  await ordinary("state");
  assert.equal(requests.at(-1).options.headers.Authorization, undefined);
  const unicode = createMedPravoClient("https://"+encodeURIComponent("владелец")+":"+encodeURIComponent("пароль")+"@cabinet.example/",transport);
  await unicode("state");
  assert.equal(requests.at(-1).options.headers.Authorization,"Basic "+Buffer.from("владелец:пароль").toString("base64"));
  const denied = createMedPravoClient("https://cabinet.example/",async()=>({ok:false,status:401}));
  await assert.rejects(denied("state"),/Требуется вход/);
  const downloader=createMedPravoClient("https://cabinet.example/",async(address,options)=>{
    assert.equal(new URL(address).pathname,"/api/file");
    assert.equal(options.credentials,"same-origin");
    return {ok:true,headers:{get:()=>"attachment; filename*=UTF-8''"+encodeURIComponent("Приказ.zip")},blob:async()=>new Blob(["PK-test"])};
  });
  const file=await downloader.download("file?url=known");
  assert.equal(file.filename,"Приказ.zip");assert.equal(await file.blob.text(),"PK-test");
  const failedDownload=createMedPravoClient("https://cabinet.example/",async()=>({ok:false,status:502,json:async()=>({error:"Источник недоступен"})}));
  await assert.rejects(failedDownload.download("file?url=known"),/Источник недоступен/);
  console.log("API browser client checks passed: authenticated links, clean addresses, GET/POST, Unicode and 401.");
})().catch(error=>{console.error(error);process.exitCode=1;});
