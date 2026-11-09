/** Supplied demo UI, connected to the shared offline contract repository. */
const Vault=(()=>{let api=null;
function init(hooks){api=mount(hooks);}
function mount(hooks){
let industry=JSON.parse(JSON.stringify(ContractFacts.industryTree));
let contracts=[],originals=[],saving=false;
const $=id=>document.getElementById("demo-"+id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// 本地扩展字段和版本化存储，不改变原有合同结构。
const serviceOptions=ServiceContent.domainNames;
let storageMessage='';
function validSaved(c){return c&&typeof c.name==='string'&&(c.amount===''||(Number.isFinite(Number(c.amount))&&Number(c.amount)>=0))&&['industry','region'].every(k=>c[k].every((v,i)=>!v||c[k].slice(0,i).every(Boolean)));}
function extendIndustry(path){const[a,b,c]=path;if(!a)return;industry[a]??={};if(b){industry[a][b]??=[];if(c&&!industry[a][b].includes(c))industry[a][b].push(c);}}
function options(el,items,label){el.replaceChildren(new Option(label,''),...items.map(x=>new Option(x,x)));}
const regionTree={'华南':{'广东':['深圳','广州','珠海'],'广西':['南宁'],'海南':['海口']},'华东':{'上海':['上海'],'江苏':['南京','苏州'],'浙江':['杭州','宁波'],'山东':['济南','青岛'],'安徽':['合肥'],'福建':['福州','厦门'],'江西':['南昌']},'华北':{'北京':['北京'],'天津':['天津'],'河北':['石家庄'],'山西':['太原'],'内蒙古':['呼和浩特']},'华中':{'湖北':['武汉'],'湖南':['长沙'],'河南':['郑州']},'西南':{'四川':['成都'],'重庆':['重庆'],'云南':['昆明'],'贵州':['贵阳'],'西藏':['拉萨']},'西北':{'陕西':['西安'],'甘肃':['兰州'],'青海':['西宁'],'宁夏':['银川'],'新疆':['乌鲁木齐']},'东北':{'辽宁':['沈阳'],'吉林':['长春'],'黑龙江':['哈尔滨']}};
function allRegionData(){const tree=JSON.parse(JSON.stringify(regionTree));contracts.forEach(c=>{if(c.region.every(Boolean)){tree[c.region[0]]??={};tree[c.region[0]][c.region[1]]??=[];if(!tree[c.region[0]][c.region[1]].includes(c.region[2]))tree[c.region[0]][c.region[1]].push(c.region[2]);}});return tree;}
function exportFields(row){
 return Object.entries(row).filter(([label])=>label!=='项目名称').map(([label,value])=>
  `<div><span>${esc(label)}</span><strong>${esc(value||'—')}</strong></div>`).join('');
}
let searchRows=[], searchTimer, requestId=0;
function cardHTML(row,index){
 const title=esc(row['项目名称']||'未识别项目');
 return `<button class="card" data-result-index="${index}" aria-label="查看${title}详情"><h3>${title}</h3><div class="facts">${exportFields(row)}</div><div class="card-bottom"><span class="detail-link">查看详情 ↗</span></div></button>`;
}
function search(delay=0){
 clearTimeout(searchTimer);
 const id=++requestId;
 const query=$('keyword').value.trim();
 searchRows=[];
 $('cards').replaceChildren();
 $('count').textContent=query?'正在查询云盘总表…':'';
 $('searchResults').hidden=!query;
 if(!query)return;
 searchTimer=setTimeout(async()=>{
  try{
   const {rows,total}=await hooks.searchCloud(query);
   if(id!==requestId)return;
   searchRows=rows;
   $('count').textContent=total>rows.length?`匹配 ${total} 份，显示前 ${rows.length} 份，请缩小搜索范围`:`${total} 份合同`;
   $('cards').innerHTML=rows.length?rows.map(cardHTML).join(''):'<div class="empty compact">云盘总表没有匹配的合同。</div>';
  }catch(error){
   if(id===requestId)$('count').textContent=error.message;
  }
 },delay);
}
$('keyword').addEventListener('input',()=>search(250));
$('searchForm').onsubmit=e=>{e.preventDefault();search();};
$('cards').addEventListener('click',e=>{
 const card=e.target.closest('[data-result-index]');
 const row=card&&searchRows[Number(card.dataset.resultIndex)];
 if(!row)return;
 $('detailTitle').textContent=row['项目名称']||'未识别项目';
 $('vaultDetailBody').innerHTML=`<div class="facts">${exportFields(row)}</div>`;
 $('detail').showModal();
});
$('close').onclick=()=>$('detail').close();$('detail').addEventListener('click',e=>{if(e.target===$('detail')){const r=$('detail').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('detail').close()}});

// 合同整理页使用独立草稿；只有成功保存才修改检索数据。
let draft=null,dirty=false,editingTag=null,draftRevision=null;
const editorGroups={keywords:'原始关键词',services:'服务领域',specificTags:'具体服务',customTags:'自定义 Tag'};
const copy=x=>JSON.parse(JSON.stringify(x));
function status(message,error=false){$('saveStatus').textContent=message;$('saveStatus').classList.toggle('error',error);}
function markDirty(){dirty=true;$('draftState').textContent='● 有未保存修改';status('草稿尚未入库，请保存后再合并到云盘总表。');}
function refreshContractPicker(){const id=draft?.id;options($('manageContract'),[], '');$('manageContract').replaceChildren(...contracts.map(c=>new Option(c.name,c.id)));if(id)$('manageContract').value=id;}
function populateEditorIndustry(){options($('editIndustry1'),Object.keys(industry),'请选择一级行业');$('editIndustry1').value=draft.industry[0];options($('editIndustry2'),Object.keys(industry[draft.industry[0]]||{}),'请选择二级行业');$('editIndustry2').value=draft.industry[1];options($('editIndustry3'),industry[draft.industry[0]]?.[draft.industry[1]]||[],'请选择三级行业');$('editIndustry3').value=draft.industry[2];}
function loadDraft(id){$('industryCustomPanel').hidden=true;[1,2,3].forEach(n=>$('industryCustom'+n).value='');draftRevision=originals.find(c=>c.id===id)?.ocrRevision;draft=copy(contracts.find(c=>c.id===id));dirty=false;editingTag=null;$('manageContract').value=id;for(const [field,key] of Object.entries({editName:'name',editAmount:'amount',editScope:'scope',editNeed:'need',editOriginal:'originalDescription',editEic:'eic',editPic:'pic',editFic:'fic',editEnterpriseSize:'enterpriseSize',editBusinessModel:'businessModel',editServiceTerm:'serviceTerm',editNotes:'notes'}))$(field).value=draft[key];$('editSystems').value=draft.systems.join('、');$('editDeliverables').value=draft.deliverables.join('\n');populateEditorIndustry();[1,2,3].forEach(n=>$('editRegion'+n).value=draft.region[n-1]);refreshEditorRegions();renderEditors();$('draftState').textContent='已载入 · '+draft.id+' · '+ContractScope.resolve(draft).label;status(storageMessage||'编辑内容仅在保存后同步到检索。',!!storageMessage);}
function renderEditors(){Object.entries(editorGroups).forEach(([key,label])=>{const values=draft[key],container=$(key+'Editor');container.innerHTML=(key==='keywords'?'':`<h3>${label}</h3>`)+`<div class="tag-list">${values.length?values.map((v,i)=>editingTag?.key===key&&editingTag.index===i?`<div class="edit-tag editing"><div class="edit-inline"><input id="demo-tagEditValue" aria-label="修改${label}" maxlength="120" value="${esc(v)}"><button type="button" data-action="confirm" data-group="${key}" data-index="${i}">确认</button><button type="button" data-action="cancel">取消</button></div></div>`:`<span class="edit-tag"><button type="button" title="点击修改" data-action="edit" data-group="${key}" data-index="${i}">${esc(v)}</button><button type="button" aria-label="删除${esc(v)}" data-action="remove" data-group="${key}" data-index="${i}">×</button></span>`).join(''):`<span class="tag-empty">暂无${label}</span>`}</div><div class="tag-add"><input id="demo-add-${key}" ${key==='services'?'list="serviceTagOptions"':''} aria-label="新增${label}" maxlength="120" placeholder="添加${label}"><button type="button" class="secondary" data-action="add" data-group="${key}">＋ 添加</button></div>`;});}
function changeTag(action,key,index){
 if(action==='cancel'){editingTag=null;renderEditors();return;}
 if(action==='edit'){editingTag={key,index};renderEditors();$('tagEditValue').focus();return;}
 if(action==='remove'){if(key==='services')draft.domainSelectionManual=true;if(key==='specificTags')draft.specificSelectionManual=true;if(key==='keywords')draft.keywordsSelectionManual=true;draft[key].splice(index,1);editingTag=null;markDirty();renderEditors();return;}
 const input=$(action==='add'?'add-'+key:'tagEditValue'),value=input.value.trim();
 if(!value){status('请输入标签内容。',true);input.focus();return;}
 if(draft[key].some((v,i)=>v.toLowerCase()===value.toLowerCase()&&(action==='add'||i!==index))){status('该分类中已存在相同内容，请勿重复添加。',true);return;}
 if(key==='services'&&!ServiceContent.isDomain(value)){status('请输入业务领域名称，ITGC 等活动请填写到具体服务。',true);return;}
 if(key==='services')draft.domainSelectionManual=true;if(key==='specificTags')draft.specificSelectionManual=true;if(key==='keywords')draft.keywordsSelectionManual=true;
 if(key==='specificTags'&&!ServiceContent.cleanTag(value)){status('请输入明确的业务名称，例如 ITGC、权限管理、数据迁移。',true);return;}
 const cleaned=key==='specificTags'?ServiceContent.cleanTag(value):key==='services'?ServiceContent.canonicalDomain(value):value;
 if(action==='add')draft[key].push(cleaned);else draft[key][index]=cleaned;
 editingTag=null;markDirty();renderEditors();
}
$('editorForm').addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(b)changeTag(b.dataset.action,b.dataset.group,Number(b.dataset.index));});
$('editorForm').addEventListener('keydown',e=>{if(e.isComposing)return;if(e.key==='Enter'&&e.target.matches('.tag-add input,.edit-inline input')){e.preventDefault();const b=e.target.parentElement.querySelector('[data-action]');changeTag(b.dataset.action,b.dataset.group,Number(b.dataset.index));}});
$('editorForm').addEventListener('input',e=>{if(!e.target.closest('.tag-add,.edit-inline'))markDirty();});
$('editorForm').addEventListener('change',e=>{if(!e.target.closest('.tag-add,.edit-inline'))markDirty();});
$('editIndustry1').onchange=()=>{options($('editIndustry2'),Object.keys(industry[$('editIndustry1').value]||{}),'请选择二级行业');options($('editIndustry3'),[],'请选择三级行业');markDirty();};
$('editIndustry2').onchange=()=>{options($('editIndustry3'),industry[$('editIndustry1').value]?.[$('editIndustry2').value]||[],'请选择三级行业');markDirty();};
function pendingInput(){if(!draft)return false;return editingTag||['keywords','services','specificTags','customTags'].some(key=>$('add-'+key).value.trim());}
$('manageContract').onchange=()=>{if(saving){$('manageContract').value=draft.id;return;}const next=$('manageContract').value;if((dirty||pendingInput())&&!confirm('当前合同有未保存内容。切换将放弃这些修改，是否继续？')){$('manageContract').value=draft.id;return;}loadDraft(next);};
$('discardDraft').onclick=()=>{if((dirty||pendingInput())&&!confirm('撤销当前合同所有未保存修改？'))return;loadDraft(draft.id);};
function mergeValues(key,values){draft[key]=[...new Set([...draft[key],...values])];}
$('extractKeywords').onclick=()=>{if(!draft)return;const text=ContractScope.category(draft)==='ey-template'?ContractScope.textFor(draft):draft.rawText||$('editOriginal').value.trim();if(!text){status(ContractScope.category(draft)==='ey-template'?'未定位附录一／工作说明书，请先核对识别全文。':'请先识别合同。',true);return;}const analyzed=draft.analysis||ServiceContent.analyze(text);draft.keywords=[...new Set(analyzed.keywords.map(x=>x.label))];draft.keywordsSelectionManual=false;editingTag=null;markDirty();renderEditors();status('已根据'+ContractScope.resolve(draft).label+'提取关键词，其他自定义信息保留。');};
$('generateTags').onclick=()=>{if(!draft)return;const analyzed=draft.analysis||ServiceContent.analyze(ContractScope.category(draft)==='ey-template'?ContractScope.textFor(draft):draft.rawText||$('editOriginal').value);draft.services=[...new Set(analyzed.serviceDomains.map(x=>x.label))];draft.specificTags=[...new Set(analyzed.services.map(x=>x.label))];draft.domainSelectionManual=false;draft.specificSelectionManual=false;editingTag=null;markDirty();renderEditors();status(ContractScope.category(draft)==='ey-template'&&!ContractScope.textFor(draft)?'未定位附录一／工作说明书，未生成自动Tag；自定义标签和笔记保留。':'已根据'+ContractScope.resolve(draft).label+'重新分类，保存后生效。');};
function updateSystemOptions(){renderDomainCatalog();$('serviceTagOptions').innerHTML=serviceOptions.map(s=>`<option value="${esc(s)}"></option>`).join('');}
function refreshEditorRegions(){const tree=allRegionData(),r=$('editRegion1').value,p=$('editRegion2').value;[Object.keys(tree),Object.keys(tree[r]||{}),tree[r]?.[p]||[]].forEach((items,i)=>$('regionOptions'+(i+1)).innerHTML=items.map(v=>`<option value="${esc(v)}"></option>`).join(''));}
$('editRegion1').oninput=()=>{$('editRegion2').value='';$('editRegion3').value='';refreshEditorRegions();markDirty();};$('editRegion2').oninput=()=>{$('editRegion3').value='';refreshEditorRegions();markDirty();};
$('editorForm').onsubmit=async e=>{e.preventDefault();if(!draft||saving)return;if(pendingInput()){status('请先确认或添加正在编辑的标签。',true);return;}const next=copy(draft);next.name=$('editName').value.trim();next.amount=$('editAmount').value===''?'':Number($('editAmount').value);next.industry=[1,2,3].map(n=>$('editIndustry'+n).value);next.systems=[...new Set($('editSystems').value.split(/[,，、\n]+/).map(x=>x.trim()).filter(Boolean))];next.region=[1,2,3].map(n=>$('editRegion'+n).value.trim());for(const[field,key]of Object.entries({editEic:'eic',editPic:'pic',editFic:'fic',editScope:'scope',editNeed:'need',editOriginal:'originalDescription',editEnterpriseSize:'enterpriseSize',editBusinessModel:'businessModel',editServiceTerm:'serviceTerm',editNotes:'notes'}))next[key]=$(field).value.trim();next.deliverables=$('editDeliverables').value.split(/\n/).map(x=>x.trim()).filter(Boolean);if(!validSaved(next)||!next.name){status('请填写合同名称、有效金额，并按顺序填写行业与区域层级。',true);return;}saving=true;$('editorForm').querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=true);try{const all=await Storage.getAllContracts(),latest=all.find(c=>c.id===next.id);if(!latest)throw Error('合同已被删除，请重新选择');if(latest.ocrRevision!==draftRevision)throw Error('识别结果已更新，请重新载入合同后保存');await Storage.updateContract(VaultModel.update(latest,next));dirty=false;editingTag=null;originals=await hooks.saved();contracts=originals.map(project);refreshContractPicker();updateSystemOptions();loadDraft(next.id);$('draftState').textContent='✓ 已保存 · '+new Date().toLocaleTimeString('zh-CN');status('保存成功：已更新本地合同库，可合并到云盘总表。');}catch(err){status('保存失败：'+err.message+'；输入已保留。',true);}finally{saving=false;$('editorForm').querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=false);}};
function showPage(page){hooks.navigate('vault-'+page);}
$('goSearch').onclick=()=>showPage('search');
function renderDomainCatalog(){const rows=DomainCatalog.list();$('domainList').innerHTML=rows.map(x=>`<div class="domain-entry"><strong>${esc(x.name)}</strong><span>${x.contractIds.length} 份合同${x.aliases.length?' · 别名：'+x.aliases.map(esc).join('、'):''}</span></div>`).join('');}
$('saveDomain').onclick=async()=>{const button=$('saveDomain');button.disabled=true;try{await DomainCatalog.define($('domainName').value.trim(),$('domainAliases').value.split(/[、,，;；]/).map(x=>x.trim()).filter(Boolean));$('domainStatus').textContent='已保存，今后合同会使用此领域及别名匹配';$('domainName').value='';$('domainAliases').value='';originals=await hooks.saved();contracts=originals.map(project);updateSystemOptions();}catch(e){$('domainStatus').textContent='保存失败：'+e.message;}finally{button.disabled=false;}};
refreshContractPicker();updateSystemOptions();
$('customIndustry').onclick=()=>{$('industryCustomPanel').hidden=!$('industryCustomPanel').hidden;};
$('applyIndustry').onclick=()=>{const path=[1,2,3].map(i=>$('industryCustom'+i).value.trim());if(!path[0]||path.some((v,i)=>v&&path.slice(0,i).some(x=>!x))){status('请按顺序填写行业分类。',true);return;}extendIndustry(path);draft.industry=path;populateEditorIndustry();$('industryCustomPanel').hidden=true;markDirty();};
function project(c){const p=VaultModel.project(c);p.industry=[0,1,2].map(i=>p.industry[i]||'');p.region=[0,1,2].map(i=>p.region[i]||'');p.content=c.content||p.scope;return p;}
function canLeave(){if(saving)return false;if(!(dirty||pendingInput()))return true;if(!confirm('当前有未保存的整理内容，是否放弃修改？'))return false;dirty=false;editingTag=null;if(contracts.some(c=>c.id===draft?.id))loadDraft(draft.id);else draft=null;return true;}
function sync(data,page){originals=data;contracts=data.map(project);contracts.forEach(c=>extendIndustry(c.industry));refreshContractPicker();updateSystemOptions();$('emptyManage').hidden=!!contracts.length;$('editorForm').hidden=!contracts.length;$('manageContract').disabled=!contracts.length;if(page==='manage'&&!(dirty||saving)){if(contracts.length)loadDraft(contracts.find(c=>c.id===draft?.id)?.id||contracts[0].id);else draft=null;}else if(page==='manage'&&dirty)status('合同库已更新，当前未保存的修改已保留。');}
window.addEventListener('beforeunload',e=>{if(dirty||pendingInput()){e.preventDefault();e.returnValue='';}});
return {render:(data,page)=>{sync(data,page);if(page==='search')search();},refresh:sync,canLeave,selectContract:id=>{if(contracts.some(c=>c.id===id)){loadDraft(id);return true;}return false;}};
}
return {init,render:(data,page)=>api.render(data,page),refresh:(data,page)=>api.refresh(data,page),canLeave:()=>api?api.canLeave():true,selectContract:id=>api?api.selectContract(id):false};
})();
