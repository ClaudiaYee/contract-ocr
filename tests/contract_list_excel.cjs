/** 我的合同（PIC/EIC 列）、合并到云盘总表（上传者ID，不含 Engagement Code / Description、来源文件、FIC）、合同检索（他人合同只读、结果内按 PIC/EIC/上传人筛选、勾选导出 Excel）；真实本机服务，仅用合成数据。 */
const assert=require('assert'),{spawn,execFileSync}=require('child_process'),{chromium}=require('playwright'),fs=require('fs'),os=require('os'),path=require('path');
const repo=path.resolve(__dirname,'..'),py=process.env.PYTHON||'python';
const pyRun=code=>execFileSync(py,['-c','import sys,json;sys.path.insert(0,'+JSON.stringify(path.join(repo,'native'))+');import excel_table as e\n'+code]).toString('utf8');
(async()=>{const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'x-')),cloud=fs.mkdtempSync(path.join(os.tmpdir(),'cloud-')),work=fs.mkdtempSync(path.join(os.tmpdir(),'xl-')),port=25000+Math.floor(Math.random()*5000),origin='http://127.0.0.1:'+port;
const executable=process.argv[2],command=executable?path.resolve(executable):py,args=executable?['--no-browser']:['native/desktop.py','--no-browser'];
const s=spawn(command,args,{cwd:repo,env:{...process.env,CONTRACT_OCR_DATA_DIR:tmp,CONTRACT_OCR_PORT:String(port),CONTRACT_OCR_CLOUD_DEFAULT:'',CONTRACT_OCR_DIAGNOSTICS:'1'}});let logs='';s.stderr.on('data',d=>logs+=d);s.stdout.on('data',d=>logs+=d);
const options={headless:true};if(process.env.OCR_TEST_CHROMIUM){options.executablePath=process.env.OCR_TEST_CHROMIUM;options.args=['--no-sandbox'];}
const b=await chromium.launch(options);
const toast=(page,text)=>page.waitForFunction(t=>[...document.querySelectorAll('.toast')].some(x=>x.textContent.includes(t)),text,{timeout:15000});
try{for(let i=0;;i++){try{if((await fetch(origin+'/api/health')).ok)break;}catch{}if(i>300||s.exitCode!==null)throw Error(logs);await new Promise(r=>setTimeout(r,100));}
const ctx=await b.newContext({acceptDownloads:true,viewport:{width:1600,height:900}});const p=await ctx.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.goto(origin);await p.waitForFunction(()=>window.__CONTRACT_OCR_READY,null,{timeout:30000});
await p.evaluate(async()=>{
 await Storage.addContract({id:'a1',projectName:'示例甲公司之SOC2类型二报告',partyA:'示例甲科技有限公司',partyB:'示例会计师事务所',signDate:'2026-10-30',amount:273000,deliverables:'一份SOC2 报告',rawText:'服务内容：SOC2类型二鉴证，出具SOC2报告，评价内部控制。',sourceFile:'示例甲-保密项目.pdf',engagementCode:'E-0001',engagementCodeDescription:'保密描述',engagementName:'Synthetic SOC engagement',knowledgeProfile:{pic:'赵六',eic:'王五',tagSchemaVersion:3},createdAt:Date.now()});
 await Storage.addContract({id:'a2',projectName:'示例乙公司ITGC审计',partyA:'示例乙股份有限公司',partyB:'示例咨询有限公司',signDate:'2026-01-02',rawText:'服务内容：开展ITGC测试和渗透测试。',knowledgeProfile:{pic:'孙八',eic:'王五',tagSchemaVersion:3},createdAt:Date.now()});
});
await p.reload();await p.waitForFunction(()=>window.__CONTRACT_OCR_READY);await p.locator('[data-view="upload"]').click();
const heads=await p.locator('#myContracts .contract-table thead th').allTextContents();assert.deepEqual(heads.map(x=>x.trim()),['项目名称','甲方','乙方','签约时间','原始关键词','PIC','EIC','操作']);
for(const removed of ['#exportBtn','.header-actions #importBtn','#exportExcelBtn','#importExcelBtn','#importExcelFile'])assert.equal(await p.locator(removed).count(),0,removed+' removed');
assert.equal(await p.locator('#myContracts #importBtn').count(),1,'backup import lives in 上传识别');
const me=(await p.evaluate(()=>NativeDocuments.request('/api/config'))).uploaderDefault;assert(me,'default uploader from this computer account');
await p.waitForTimeout(500);const cells=await p.locator('tr[data-id="a1"] td').allTextContents();assert(!cells.join('').includes('27.30'));assert(cells.join('').includes('赵六'));
// 云盘总表：旧版本格式（含 Engagement Code / Description、来源文件、FIC）+ 他人上传、只有关键词的行
const master=path.join(cloud,'合同识别总表.xlsx');
pyRun('h=["项目名称","上传者ID","Engagement Code","Engagement Code Description","甲方","原始关键词","服务领域","PIC","EIC","FIC","来源文件","合同ID"];open('+JSON.stringify(master)+',"wb").write(e.write_xlsx(h,[{"项目名称":"他人SOC2项目","上传者ID":"GV371QP","Engagement Code":"E-9","Engagement Code Description":"secret","甲方":"丙公司","原始关键词":"SOC2类型二鉴证；SOC2报告；内部控制","PIC":"周九","FIC":"x","来源文件":"丙-IPO.pdf","合同ID":"remote-gv"}]))');
const cloudUpload=async()=>{await p.locator('[data-ok]').click();};
await p.locator('#cloudMergeBtn').click();await cloudUpload();await toast(p,'设置');
await p.locator('#cfgCloudExcel').fill(cloud);await p.locator('#saveCloudExcelBtn').click();await p.waitForFunction(()=>document.getElementById('cloudExcelState').textContent.includes('已保存'));
await p.reload();await p.waitForFunction(()=>window.__CONTRACT_OCR_READY);await p.locator('[data-view="settings"]').click();await p.waitForFunction(v=>document.getElementById('cfgCloudExcel').value===v,cloud);
await p.locator('[data-view="upload"]').click();await p.locator('#cloudMergeBtn').click();await cloudUpload();await toast(p,'新增 2 行');
const readMaster=file=>JSON.parse(pyRun('h,r=e.read_xlsx(open('+JSON.stringify(file)+',"rb").read());sys.stdout.buffer.write(json.dumps({"h":h,"r":r}).encode())'));
let m=readMaster(master);console.log(m.h,m.r.map(r=>[r['项目名称'],r['服务领域'],r['具体服务']]));
for(const column of ['Engagement Code','Engagement Code Description','来源文件','FIC'])assert(!m.h.includes(column),column+' must not be in the shared master');
assert(!JSON.stringify(m.r).includes('保密')&&!JSON.stringify(m.r).includes('IPO')&&!JSON.stringify(m.r).includes('secret'),'sensitive values scrubbed');
assert.equal(m.r.find(r=>r['合同ID']==='a1')['Engagement Name'],'Synthetic SOC engagement');assert.equal(m.r.find(r=>r['合同ID']==='a1')['上传者ID'],me);assert(m.r.find(r=>r['合同ID']==='a1')['服务领域'],'service domains filled');assert(m.r.find(r=>r['合同ID']==='a1')['具体服务']);
assert.equal(m.r.find(r=>r['合同ID']==='remote-gv')['上传者ID'],'GV371QP');assert(fs.readdirSync(cloud).some(f=>f.includes('备份')));
// hand-added column survives a second merge
pyRun('h,r=e.read_xlsx(open('+JSON.stringify(master)+',"rb").read());h.append("备注");r[0]["备注"]="手填";open('+JSON.stringify(master)+',"wb").write(e.write_xlsx(h,r))');
await p.locator('#cloudMergeBtn').click();await cloudUpload();await toast(p,'更新 2 行');m=readMaster(master);assert(m.h.includes('备注'));assert(m.r.some(r=>r['备注']==='手填'));
// 合同检索：本机合同 + 他人上传（只读）；结果内按 PIC / EIC / 上传人筛选，勾选后导出 Excel
await p.locator('[data-view="vault-search"]').click();
assert(!(await p.locator('#demo-searchResults').isVisible()));
await p.locator('#demo-keyword').fill('SOC2');
const remoteRow=p.locator('#demo-resultBody tr.row-remote').filter({hasText:'他人SOC2项目'});
await remoteRow.waitFor();await p.locator('#demo-resultBody tr[data-id="a1"]').waitFor();
assert.deepEqual((await p.locator('#demo-searchResults thead th').allTextContents()).map(x=>x.trim()),['','项目名称','甲方','乙方','签约时间','原始关键词','PIC','EIC','上传人','操作']);
assert((await remoteRow.innerText()).includes('只读'));assert((await remoteRow.innerText()).includes('GV371QP'));assert.equal(await remoteRow.locator('[data-edit]').count(),0);
assert((await p.locator('#demo-resultBody tr[data-id="a1"]').innerText()).includes(me),'local rows show this computer as uploader');
await remoteRow.locator('[data-row]').click();
const facts=await p.locator('#demo-vaultDetailBody .facts span').allTextContents();assert(facts.includes('上传者ID'));for(const hidden of ['Engagement Code','Engagement Code Description','来源文件','合同ID','FIC'])assert(!facts.includes(hidden),hidden+' hidden');
const groups=await p.locator('#demo-vaultDetailBody .remote-tag-row').evaluateAll(rows=>rows.map(r=>r.dataset.group));assert(groups.includes('服务领域'),'domains derived from keywords: '+groups);assert(groups.includes('原始关键词'));
await p.locator('#demo-close').click();
await p.locator('#demo-rfUploader').selectOption('GV371QP');await p.waitForFunction(()=>document.querySelectorAll('#demo-resultBody tr[data-index]').length===1&&document.querySelector('#demo-resultBody tr.row-remote'));
await p.locator('#demo-rfUploader').selectOption('');await p.locator('#demo-rfPic').selectOption('赵六');await p.waitForFunction(()=>document.querySelectorAll('#demo-resultBody tr[data-index]').length===1&&document.querySelector('#demo-resultBody tr[data-id="a1"]'));
await p.locator('#demo-rfPic').selectOption('');await p.waitForFunction(()=>document.querySelectorAll('#demo-resultBody tr[data-index]').length===2);
await remoteRow.locator('[data-select]').check();assert((await p.locator('#demo-selectedCount').innerText()).includes('已勾选 1'));
const exportFile=async name=>{const [dl]=await Promise.all([p.waitForEvent('download'),p.locator('#demo-exportResults').click()]);const file=path.join(work,name);await dl.saveAs(file);return readMaster(file);};
let x=await exportFile('picked.xlsx');assert.equal(x.r.length,1);assert.equal(x.r[0]['合同ID'],'remote-gv');assert.equal(x.r[0]['上传者ID'],'GV371QP','others keep their uploader id');assert(!x.h.includes('来源文件')&&!x.h.includes('Engagement Code')&&!x.h.includes('FIC'));
await remoteRow.locator('[data-select]').uncheck();x=await exportFile('all.xlsx');assert.equal(x.r.length,2);assert.equal(x.r.find(r=>r['合同ID']==='a1')['上传者ID'],me);
await p.locator('#demo-selectAll').check();assert((await p.locator('#demo-selectedCount').innerText()).includes('已勾选 2'));await p.locator('#demo-selectAll').uncheck();
// 切换云盘路径后检索跟随
const otherMaster=path.join(work,'other-master.xlsx');
pyRun('open('+JSON.stringify(otherMaster)+',"wb").write(e.write_xlsx(e.COLUMNS,[{"\\u9879\\u76ee\\u540d\\u79f0":"other from second master","\\u4e0a\\u4f20\\u8005ID":"\\u540c\\u4e8b\\u4e59","\\u5408\\u540cID":"remote-1"}]))');
await p.locator('[data-view="settings"]').click();
await p.waitForFunction(v=>document.getElementById('cfgCloudExcel').value===v&&!document.getElementById('saveCfgBtn').disabled,cloud);
await p.locator('#cfgCloudExcel').fill(otherMaster);
await p.locator('#saveCloudExcelBtn').click();
await p.waitForFunction(()=>document.getElementById('cloudExcelState').textContent.includes('已保存'));
await p.locator('[data-view="vault-search"]').click();
await p.locator('#demo-keyword').fill('other');
const second=p.locator('#demo-resultBody tr.row-remote').filter({hasText:'other from second master'});
await second.waitFor({timeout:5000}).catch(async error=>{console.error(await p.locator('#demo-summary').innerText(),await p.locator('#demo-resultBody').innerText());throw error;});
assert.equal(await p.locator('#demo-resultBody tr.row-remote').count(),1);await second.locator('[data-row]').click();assert((await p.locator('#demo-vaultDetailBody').innerText()).includes('同事乙'));await p.locator('#demo-close').click();
// 多个关键词：逗号 / 分号 / 空格分隔；全部包含 vs 包含任一
await p.locator('#demo-keyword').fill('other，second');
await p.waitForFunction(()=>document.querySelectorAll('#demo-resultBody tr.row-remote').length===1&&!document.getElementById('demo-summary').textContent.includes('正在'));
await p.locator('#demo-keyword').fill('second；示例甲');
await p.waitForFunction(()=>document.querySelector('#demo-resultBody .empty-row')&&!document.getElementById('demo-summary').textContent.includes('正在'));
await p.locator('#demo-matchMode').selectOption('any');
await p.waitForFunction(()=>document.querySelector('#demo-resultBody tr[data-id="a1"]')&&document.querySelectorAll('#demo-resultBody tr.row-remote').length===1&&!document.getElementById('demo-summary').textContent.includes('正在'));
assert.equal(await p.locator('#demo-resultBody mark').filter({hasText:'second'}).count()>0,true);
await p.locator('#demo-matchMode').selectOption('all');
await p.locator('#demo-keyword').fill('');
await p.waitForFunction(()=>document.getElementById('demo-searchResults').hidden);
// 我的合同只显示本机合同；筛选框仍可用
await p.locator('[data-view="upload"]').click();await p.locator('#searchInput').fill('示例乙');await p.waitForFunction(()=>document.querySelectorAll('#contractTableBody tr[data-id]').length===1);await p.locator('#searchInput').fill('');
// 编辑弹窗：无金额、企业规模、FIC、Engagement Code / Description；关键词与 Tag 只读，系统可添加
await p.locator('tr[data-id="a1"] [data-action="edit"]').click();await p.locator('#demo-editorDialog').waitFor({state:'visible'});
for(const removed of ['#demo-editAmount','#demo-editEnterpriseSize','#demo-editFic','#demo-editEngagementCode','#demo-editEngagementCodeDescription'])assert.equal(await p.locator(removed).count(),0,removed+' removed');
for(const id of ['#demo-add-keywords','#demo-add-services','#demo-add-specificTags','#demo-generateTags','#demo-extractKeywords','#demo-keywordsEditor button','#demo-specificTagsEditor button','#demo-servicesEditor button'])assert.equal(await p.locator(id).count(),0,id+' must be read-only');await p.locator('#demo-add-systems').fill('Workday');await p.locator('#demo-add-systems').press('Enter');
await p.locator('#demo-editorForm [type=submit]').click();await p.locator('#demo-editorDialog').waitFor({state:'hidden'});
const edited=await p.evaluate(async()=>(await Storage.getAllContracts()).find(c=>c.id==='a1'));assert(edited.knowledgeProfile.systems.includes('Workday'));assert.equal(edited.uploadedByName,me);
assert.deepEqual(errs,[]);console.log('ALL PASS');
}catch(error){console.error(logs.slice(-3000));throw error;}finally{await b.close();s.kill();}})().catch(e=>{console.error(e);process.exit(1)});
