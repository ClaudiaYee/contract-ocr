/** Contract list: keyword/PIC/EIC/FIC columns, Excel export → import → cloud-folder master merge, through the real local server. Synthetic data only. */
const assert=require('assert'),{spawn,execFileSync}=require('child_process'),{chromium}=require('playwright'),fs=require('fs'),os=require('os'),path=require('path');
const repo=path.resolve(__dirname,'..'),py=process.env.PYTHON||'python';
const pyRun=code=>execFileSync(py,['-c','import sys,json;sys.path.insert(0,'+JSON.stringify(path.join(repo,'native'))+');import excel_table as e\n'+code]).toString('utf8');
(async()=>{const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'x-')),cloud=fs.mkdtempSync(path.join(os.tmpdir(),'cloud-')),work=fs.mkdtempSync(path.join(os.tmpdir(),'xl-')),port=25000+Math.floor(Math.random()*5000),origin='http://127.0.0.1:'+port;
const executable=process.argv[2],command=executable?path.resolve(executable):py,args=executable?['--no-browser']:['native/desktop.py','--no-browser'];
const s=spawn(command,args,{cwd:repo,env:{...process.env,CONTRACT_OCR_DATA_DIR:tmp,CONTRACT_OCR_PORT:String(port),CONTRACT_OCR_DIAGNOSTICS:'1'}});let logs='';s.stderr.on('data',d=>logs+=d);s.stdout.on('data',d=>logs+=d);
const options={headless:true};if(process.env.OCR_TEST_CHROMIUM){options.executablePath=process.env.OCR_TEST_CHROMIUM;options.args=['--no-sandbox'];}
const b=await chromium.launch(options);
const toast=(page,text)=>page.waitForFunction(t=>[...document.querySelectorAll('.toast')].some(x=>x.textContent.includes(t)),text,{timeout:15000});
try{for(let i=0;;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}if(i>300||s.exitCode!==null)throw Error(logs);await new Promise(r=>setTimeout(r,100));}
const ctx=await b.newContext({acceptDownloads:true,viewport:{width:1600,height:900}});const p=await ctx.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.goto(origin);await p.waitForFunction(()=>window.__CONTRACT_OCR_READY,null,{timeout:30000});
await p.evaluate(async()=>{await Storage.addContract({id:'a1',projectName:'广州视睿电子科技有限公司之SOC2类型二报告',partyA:'广州视睿电子科技有限公司',partyB:'安永华明会计师事务所',signDate:'2026-10-30',amount:273000,deliverables:'一份SOC2 报告',rawText:'服务内容：SOC2类型二鉴证，出具SOC2报告，评价内部控制。EIC：王五 PIC：赵六',createdAt:Date.now()});});
await p.reload();await p.waitForFunction(()=>window.__CONTRACT_OCR_READY);await p.locator('[data-view="list"]').click();
const heads=await p.locator('.contract-table thead th').allTextContents();assert.deepEqual(heads.map(x=>x.trim()),['项目名称','甲方','乙方','签约时间','原始关键词','PIC','EIC','FIC','操作']);
await p.waitForTimeout(500);const row=p.locator('tr[data-id="a1"]');const cells=await row.locator('td').allTextContents();console.log('row',cells.map(x=>x.trim().replace(/\s+/g,' ')));
assert(!cells.join('').includes('27.30'));
// export
const [dl]=await Promise.all([p.waitForEvent('download'),p.locator('#exportExcelBtn').click()]);const xfile=path.join(work,'export.xlsx'),ifile=path.join(work,'import.xlsx');await dl.saveAs(xfile);console.log('download',dl.suggestedFilename());
const parsed=JSON.parse(pyRun('h,r=e.read_xlsx(open('+JSON.stringify(xfile)+',"rb").read());sys.stdout.buffer.write(json.dumps({"h":h,"r":r}).encode())'));console.log(parsed);
assert.equal(parsed.r[0]['合同ID'],'a1');
// modify: FIC on a1, keywords, plus a new row
pyRun('h,r=e.read_xlsx(open('+JSON.stringify(xfile)+',"rb").read());r[0]["FIC"]="\\u94b1\\u4e03";r[0]["\\u4e59\\u65b9"]="";r.append({"\\u9879\\u76ee\\u540d\\u79f0":"\\u65b0\\u5bfc\\u5165\\u9879\\u76ee","\\u7532\\u65b9":"\\u7532\\u516c\\u53f8","\\u7b7e\\u7ea6\\u65f6\\u95f4":"2026-01-02","\\u539f\\u59cb\\u5173\\u952e\\u8bcd":"ITGC\\uff1b\\u6e17\\u900f\\u6d4b\\u8bd5","PIC":"\\u5b59\\u516b"});open('+JSON.stringify(ifile)+',"wb").write(e.write_xlsx(e.COLUMNS,r))');
await p.locator('#importExcelFile').setInputFiles(ifile);await toast(p,'新增 1 份，更新 1 份');
await p.waitForFunction(()=>document.querySelectorAll('#contractTableBody tr[data-id]').length===2);
const a1=(await p.locator('tr[data-id="a1"] td').allTextContents()).map(x=>x.trim());console.log('a1 after',a1);assert(a1.includes('钱七'));assert(a1.includes('安永华明会计师事务所'),'blank cell must not erase');
const newRow=p.locator('#contractTableBody tr[data-id]').filter({hasText:'新导入项目'});const nr=(await newRow.locator('td').allTextContents()).map(x=>x.trim().replace(/\s+/g,' '));console.log('new',nr);assert(nr.includes('孙八'));assert(nr.join(' ').includes('ITGC'));
// reimport same file: no changes
await p.locator('#importExcelFile').setInputFiles(ifile);await toast(p,'无变化 2');
// cloud merge without path -> goes to settings
await p.locator('#cloudMergeBtn').click();await toast(p,'设置');
await p.locator('#cfgCloudExcel').fill(cloud);await p.locator('#saveCloudExcelBtn').click();await p.waitForFunction(()=>document.getElementById('cloudExcelState').textContent.includes('已保存'));
await p.reload();await p.waitForFunction(()=>window.__CONTRACT_OCR_READY);await p.locator('[data-view="settings"]').click();await p.waitForFunction(v=>document.getElementById('cfgCloudExcel').value===v,cloud);
await p.locator('[data-view="list"]').click();await p.locator('#cloudMergeBtn').click();await toast(p,'新增 2 行');
// hand-add a column + row in master, then merge again
const master=path.join(cloud,'合同识别总表.xlsx');
pyRun('h,r=e.read_xlsx(open('+JSON.stringify(master)+',"rb").read());h.append("\\u5907\\u6ce8");r[0]["\\u5907\\u6ce8"]="\\u624b\\u586b";r.append({"\\u9879\\u76ee\\u540d\\u79f0":"other","\\u7532\\u65b9":"X"});open('+JSON.stringify(master)+',"wb").write(e.write_xlsx(h,r))');
await p.locator('#cloudMergeBtn').click();await toast(p,'更新 2 行');
const m=JSON.parse(pyRun('h,r=e.read_xlsx(open('+JSON.stringify(master)+',"rb").read());sys.stdout.buffer.write(json.dumps({"h":h,"r":r}).encode())'));console.log(m.h,m.r.map(r=>[r['项目名称'],r['FIC'],r['备注']]));
assert.equal(m.r.length,3);assert(m.h.includes('备注'));assert(m.r.some(r=>r['备注']==='手填'));assert(fs.readdirSync(cloud).some(f=>f.includes('备份')));
// vault edit FIC
await p.locator('[data-view="vault-manage"]').click();await p.locator('#demo-manageContract').selectOption('a1');assert.equal(await p.locator('#demo-editFic').inputValue(),'钱七');
assert.deepEqual(errs,[]);console.log('ALL PASS');
}catch(error){console.error(logs.slice(-3000));throw error;}finally{await b.close();s.kill();}})().catch(e=>{console.error(e);process.exit(1)});
