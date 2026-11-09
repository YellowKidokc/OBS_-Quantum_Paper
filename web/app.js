const $ = id => document.getElementById(id);
let library, selectedFolder, current, originalText, operation;
const status = text => $('status').textContent = text;
async function api(path, data) {
  const response = await fetch('/api/' + path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) throw Error(value.error);
  return value;
}
function button(text, action, parent) {
  const node = document.createElement('button'); node.textContent = text;
  node.onclick = () => Promise.resolve(action()).catch(e => status(e.message)); parent.append(node); return node;
}
function safeToLeave() { return !current || $('editor').value === originalText || confirm('Discard unsaved edits?'); }
async function refresh() {
  library = await api('library'); $('tree').replaceChildren();
  for (const vault of library.vaults) {
    const heading = document.createElement('h2'); heading.textContent = vault.name; $('tree').append(heading);
    for (const folder of vault.folders) {
      const node = button(folder || 'All at vault root', () => {selectedFolder={vault:vault.id,folder}; renderPapers();}, $('tree'));
      node.style.paddingLeft = `${10 + folder.split('/').length * 8}px`;
    }
  }
  if (!selectedFolder && library.vaults.length) selectedFolder={vault:library.vaults[0].id,folder:''};
  renderPapers();
}
function renderPapers() {
  $('papers').replaceChildren();
  const query = $('search').value.toLowerCase();
  $('folderTitle').textContent = query ? 'Search results' : (selectedFolder?.folder || 'Vault root');
  for (const paper of library.papers) {
    const physical = paper.vault === selectedFolder?.vault && paper.path.split('/').slice(0,-1).join('/') === selectedFolder.folder;
    const virtual = library.locations.some(l => l.paper === paper.id && l.vault === selectedFolder?.vault && l.folder === selectedFolder.folder);
    if (query ? paper.path.toLowerCase().includes(query) : physical || virtual)
      button(`${paper.path.split('/').pop()}${virtual && !physical ? ' ↗' : ''}`, () => openPaper(paper.id), $('papers'));
  }
  if (!$('papers').children.length) $('papers').textContent='No registered papers here.';
}
async function openPaper(id) {
  if (!safeToLeave()) return;
  const paper = await api('paper/' + encodeURIComponent(id)); current=paper; originalText=paper.content;
  $('title').textContent=paper.path.split('/').pop();
  $('origin').textContent=`Original: ${library.vaults.find(v=>v.id===paper.vault)?.name} / ${paper.path}`;
  $('editor').hidden=false; $('actions').hidden=false; $('editor').value=paper.content;
  history.replaceState(null,'','#paper='+paper.id); renderLinks(); status('');
}
function renderLinks() {
  $('links').replaceChildren();
  for (const match of $('editor').value.matchAll(/\[([^\]]+)\]\(#paper=([a-zA-Z0-9-]+)\)/g)) {
    const a=document.createElement('a'); a.textContent=match[1]; a.href='#paper='+match[2];
    a.onclick=e=>{e.preventDefault();openPaper(match[2]).catch(e=>status(e.message));}; $('links').append(a);
  }
}
$('search').oninput=renderPapers; $('editor').oninput=renderLinks;
$('save').onclick=async()=>{try{await api('save',{paper:current.id,content:$('editor').value});originalText=$('editor').value;status('Original saved. Every location opens this same file.');}catch(e){status(e.message);}};
for (const action of ['show','move']) $(action).onclick=()=>{
  operation=action; $('dialogTitle').textContent=action==='show'?'Show this paper in another folder':'Move the original file'; $('places').replaceChildren();
  for(const vault of library.vaults) for(const folder of vault.folders){const option=document.createElement('option');option.value=JSON.stringify({vault:vault.id,folder});option.textContent=vault.name+' / '+(folder||'(root)');$('places').append(option);}
  $('destination').showModal();
};
$('destination').addEventListener('close',async()=>{if($('destination').returnValue!=='default')return;try{
  if(operation==='move'&&!safeToLeave())return;
  await api(operation,{paper:current.id,...JSON.parse($('places').value)});await refresh();
  if(operation==='move')await openPaper(current.id);
  status(operation==='show'?'Folder membership added. No duplicate created.':'Original moved. Its permanent link still works.');
}catch(e){status(e.message);}});
$('link').onclick=async()=>{try{await navigator.clipboard.writeText(location.origin+'/#paper='+current.id);status('Permanent link copied.');}catch{status('Link: '+location.origin+'/#paper='+current.id);}};
$('register').onclick=async()=>{if(!selectedFolder)return;const path=prompt('Markdown path relative to this vault:',(selectedFolder.folder?selectedFolder.folder+'/':'')+'');if(!path)return;try{const result=await api('register',{vault:selectedFolder.vault,path});await refresh();await openPaper(result.id);}catch(e){status(e.message);}};
window.addEventListener('beforeunload',e=>{if(current&&$('editor').value!==originalText){e.preventDefault();e.returnValue='';}});
await refresh().catch(e=>status(e.message));
if(location.hash.startsWith('#paper='))await openPaper(location.hash.slice(7)).catch(e=>status(e.message));
