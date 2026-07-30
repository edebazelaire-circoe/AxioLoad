const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const SETTINGS_STORAGE_KEY = 'axioload.settings.v1';
const DEFAULT_API_SERVICES = [
  {id:'routes', service:'Service d’itinéraires', purpose:'Préparation d’une future connexion à un calculateur de distances ou d’itinéraires.', key:''},
  {id:'maps', service:'Service cartographique', purpose:'Préparation d’une future connexion à un fond de carte ou à un service de géocodage.', key:''}
];
const state = { result: null, currentRequest: null, itemMeta: {}, selected: 0, selectedVehicle: 0, explicitSolutionSelection: false, selectedPlacementId: null, angle: -0.72, tilt: 0.52, zoom: 1.45, panX: 0, panY: 0, hitAreas: [], drag: null, vehicles: window.PLO_VEHICLES || [], currentTab:'vehicles', lastMainTab:'vehicles', historyCache: [] };

function clone(value){ return JSON.parse(JSON.stringify(value)); }
function loadAppSettings(){
  const defaults={theme:'light',account:{username:'Utilisateur AxioLoad',passwordHash:'',passwordSalt:''},apiKeys:clone(DEFAULT_API_SERVICES)};
  try{
    const saved=JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY)||'{}');
    return {
      theme:saved.theme==='dark'?'dark':'light',
      account:{...defaults.account,...(saved.account||{})},
      apiKeys:Array.isArray(saved.apiKeys)?saved.apiKeys.map(entry=>({id:String(entry.id||`api_${Date.now()}`),service:String(entry.service||''),purpose:String(entry.purpose||''),key:String(entry.key||'')})):defaults.apiKeys
    };
  }catch(_){ return defaults; }
}
let appSettings=loadAppSettings();
function persistAppSettings(){ localStorage.setItem(SETTINGS_STORAGE_KEY,JSON.stringify(appSettings)); }
function showSettingsMessage(selector,message,error=false){
  const box=$(selector); if(!box)return; box.textContent=message; box.classList.toggle('hidden',!message); box.classList.toggle('error',Boolean(error)); box.classList.toggle('success',Boolean(message)&&!error);
}
function applyTheme(theme,{persist=false}={}){
  const normalized=theme==='dark'?'dark':'light';
  document.documentElement.dataset.theme=normalized;
  const meta=document.querySelector('meta[name="theme-color"]'); if(meta)meta.content=normalized==='dark'?'#0A202A':'#063B5B';
  $$('input[name="theme"]').forEach(input=>{input.checked=input.value===normalized;});
  if(persist){appSettings.theme=normalized;persistAppSettings();}
  if(state.result && typeof drawViewer==='function')drawViewer();
}

function switchTab(name) {
  if(name!=='settings')state.lastMainTab=name;
  state.currentTab=name;
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
  $('#open-settings')?.classList.toggle('active',name==='settings');
  if (name === 'history') loadHistory();
  if (name === 'vehicles') renderVehicleRows();
  if (name === 'settings') renderDashboard();
}
$$('.tab').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.tab)));
$('#open-settings').addEventListener('click',()=>switchTab('settings'));
$('#close-settings').addEventListener('click',()=>switchTab(state.lastMainTab||'vehicles'));

const tooltip=$('#global-tooltip');
let pinnedHelp=null;
function positionTooltip(trigger){
  const rect=trigger.getBoundingClientRect(),gap=9;
  tooltip.style.left='0px';tooltip.style.top='0px';tooltip.hidden=false;
  const width=tooltip.offsetWidth,height=tooltip.offsetHeight;
  let left=Math.min(window.innerWidth-width-12,Math.max(12,rect.left+rect.width/2-width/2));
  let top=rect.bottom+gap;
  if(top+height>window.innerHeight-12)top=Math.max(12,rect.top-height-gap);
  tooltip.style.left=`${left}px`;tooltip.style.top=`${top}px`;
}
function showTooltip(trigger){
  if(!trigger?.dataset.tooltip)return;
  tooltip.textContent=trigger.dataset.tooltip;trigger.classList.add('open');positionTooltip(trigger);
}
function hideTooltip(trigger){
  if(trigger && pinnedHelp===trigger)return;
  trigger?.classList.remove('open');tooltip.hidden=true;
}
function bindHelpTip(trigger){
  if(!trigger || trigger.dataset.helpBound==='1')return;
  trigger.dataset.helpBound='1';
  trigger.addEventListener('mouseenter',()=>showTooltip(trigger));
  trigger.addEventListener('mouseleave',()=>hideTooltip(trigger));
  trigger.addEventListener('focus',()=>showTooltip(trigger));
  trigger.addEventListener('blur',()=>hideTooltip(trigger));
  trigger.addEventListener('click',event=>{
    event.preventDefault();event.stopPropagation();
    if(pinnedHelp===trigger){pinnedHelp=null;trigger.classList.remove('open');tooltip.hidden=true;return;}
    pinnedHelp?.classList.remove('open');pinnedHelp=trigger;showTooltip(trigger);
  });
}
function bindHelpTips(root=document){root.querySelectorAll('.help-tip').forEach(bindHelpTip);}
bindHelpTips();
document.addEventListener('click',()=>{if(pinnedHelp){pinnedHelp.classList.remove('open');pinnedHelp=null;tooltip.hidden=true;}});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&pinnedHelp){pinnedHelp.classList.remove('open');pinnedHelp=null;tooltip.hidden=true;}});
window.addEventListener('resize',()=>{if(pinnedHelp)positionTooltip(pinnedHelp);else tooltip.hidden=true;});
window.addEventListener('scroll',()=>{if(pinnedHelp)positionTooltip(pinnedHelp);else tooltip.hidden=true;},{passive:true});

function bytesToHex(bytes){return [...new Uint8Array(bytes)].map(byte=>byte.toString(16).padStart(2,'0')).join('');}
function randomSalt(){
  if(window.crypto?.getRandomValues){const bytes=new Uint8Array(16);window.crypto.getRandomValues(bytes);return bytesToHex(bytes);}
  return `${Date.now()}_${Math.random().toString(36).slice(2)}`;
}
async function hashPassword(password,salt){
  const value=`${salt}:${password}`;
  if(window.crypto?.subtle){return bytesToHex(await window.crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));}
  let hash=2166136261;for(let index=0;index<value.length;index++){hash^=value.charCodeAt(index);hash=Math.imul(hash,16777619);}return `fallback_${(hash>>>0).toString(16)}`;
}
function renderAccountSettings(){
  $('#current-username').value=appSettings.account.username||'Utilisateur AxioLoad';
  $('#new-username').value=appSettings.account.username||'Utilisateur AxioLoad';
}
$('#account-form').addEventListener('submit',async event=>{
  event.preventDefault();showSettingsMessage('#account-message','');
  const username=$('#new-username').value.trim(),current=$('#current-password').value,newPassword=$('#new-password').value,confirmation=$('#confirm-password').value;
  try{
    if(!username)throw new Error('Le nom d’utilisateur ne peut pas être vide.');
    if(appSettings.account.passwordHash){
      const currentHash=await hashPassword(current,appSettings.account.passwordSalt);
      if(currentHash!==appSettings.account.passwordHash)throw new Error('Le mot de passe actuel est incorrect.');
    }
    if(newPassword||confirmation){
      if(newPassword.length<8)throw new Error('Le nouveau mot de passe doit contenir au moins 8 caractères.');
      if(newPassword!==confirmation)throw new Error('La confirmation ne correspond pas au nouveau mot de passe.');
      const salt=randomSalt();appSettings.account.passwordSalt=salt;appSettings.account.passwordHash=await hashPassword(newPassword,salt);
    }
    appSettings.account.username=username;persistAppSettings();renderAccountSettings();
    $('#current-password').value='';$('#new-password').value='';$('#confirm-password').value='';
    showSettingsMessage('#account-message','Les informations du compte local ont été enregistrées.');
  }catch(error){showSettingsMessage('#account-message',error.message||String(error),true);}
});
$$('.password-toggle').forEach(button=>button.addEventListener('click',()=>{
  const input=$(`#${button.dataset.target}`),show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'Masquer':'Afficher';button.setAttribute('aria-label',`${show?'Masquer':'Afficher'} le mot de passe`);
}));
$$('input[name="theme"]').forEach(input=>input.addEventListener('change',()=>applyTheme(input.value,{persist:true})));
$('#save-appearance').addEventListener('click',()=>{
  const selected=$('input[name="theme"]:checked')?.value||'light';applyTheme(selected,{persist:true});showSettingsMessage('#appearance-message',`Le mode ${selected==='dark'?'sombre':'clair'} est enregistré.`);
});
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));}
function newApiKeyEntry(){return {id:`api_${Date.now()}_${Math.random().toString(36).slice(2,7)}`,service:'Nouveau service',purpose:'Décrivez ici le rôle prévu de cette future connexion.',key:''};}
function renderApiKeys(){
  const list=$('#api-key-list');list.innerHTML='';
  if(!appSettings.apiKeys.length){list.innerHTML='<div class="api-empty">Aucun service préparé. Utilisez « Ajouter un service » pour créer une ligne.</div>';return;}
  appSettings.apiKeys.forEach(entry=>{
    const row=document.createElement('div');row.className='api-key-row';row.dataset.id=entry.id;
    row.innerHTML=`<div class="api-key-fields"><label>Nom du service<input data-api="service" value="${escapeHtml(entry.service)}" maxlength="100"></label><label>Rôle prévu<input data-api="purpose" value="${escapeHtml(entry.purpose)}" maxlength="220"></label><label>Clé API<span class="password-field"><input data-api="key" type="password" value="${escapeHtml(entry.key)}" autocomplete="off" placeholder="Clé confidentielle"><button type="button" class="api-key-toggle password-toggle">Afficher</button></span></label></div><div class="api-key-actions"><button type="button" class="secondary small api-save">Enregistrer</button><button type="button" class="row-delete api-delete">Supprimer</button></div>`;
    row.querySelector('.api-key-toggle').addEventListener('click',event=>{const input=row.querySelector('[data-api="key"]'),show=input.type==='password';input.type=show?'text':'password';event.currentTarget.textContent=show?'Masquer':'Afficher';});
    row.querySelector('.api-save').addEventListener('click',()=>{
      const service=row.querySelector('[data-api="service"]').value.trim(),purpose=row.querySelector('[data-api="purpose"]').value.trim(),key=row.querySelector('[data-api="key"]').value;
      if(!service)return showSettingsMessage('#api-message','Indiquez le nom du service avant d’enregistrer.',true);
      const target=appSettings.apiKeys.find(item=>item.id===entry.id);Object.assign(target,{service,purpose,key});persistAppSettings();showSettingsMessage('#api-message',`La clé de « ${service} » est enregistrée localement. Elle n’est utilisée par aucun calcul.`);
    });
    row.querySelector('.api-delete').addEventListener('click',()=>{
      if(!confirm(`Supprimer la clé préparatoire « ${entry.service} » ?`))return;
      appSettings.apiKeys=appSettings.apiKeys.filter(item=>item.id!==entry.id);persistAppSettings();renderApiKeys();showSettingsMessage('#api-message','Le service et sa clé locale ont été supprimés.');
    });
    list.append(row);
  });
}
$('#add-api-key').addEventListener('click',()=>{appSettings.apiKeys.push(newApiKeyEntry());persistAppSettings();renderApiKeys();});
applyTheme(appSettings.theme);
renderAccountSettings();
renderApiKeys();

const vehicleFields = ['model_id','name','interior_length_mm','interior_width_mm','interior_height_mm','linear_meter_width_mm','payload_kg','door_width_mm','door_height_mm'];
function vehicleRowTemplate(vehicle = {}) {
  const tr = document.createElement('tr');
  const exists = Boolean(vehicle.version);
  tr.dataset.original = JSON.stringify(vehicle);
  tr.innerHTML = `
    <td><input data-v="model_id" value="${vehicle.model_id ?? `vehicle_${Date.now()}`}" ${exists?'readonly':''}></td>
    <td><input data-v="name" value="${vehicle.name ?? 'Nouveau véhicule'}"></td>
    <td><input data-v="interior_length_mm" type="number" min="1" value="${vehicle.interior_length_mm ?? 6000}"></td>
    <td><input data-v="interior_width_mm" type="number" min="1" value="${vehicle.interior_width_mm ?? 2400}"></td>
    <td><input data-v="interior_height_mm" type="number" min="1" value="${vehicle.interior_height_mm ?? 2500}"></td>
    <td><input data-v="linear_meter_width_mm" type="number" min="1" value="${vehicle.linear_meter_width_mm ?? 2400}"></td>
    <td><input data-v="payload_kg" type="number" min="1" step="0.1" value="${vehicle.payload_kg ?? 10000}"></td>
    <td><input data-v="door_width_mm" type="number" min="1" value="${vehicle.door_width_mm ?? vehicle.interior_width_mm ?? 2400}"></td>
    <td><input data-v="door_height_mm" type="number" min="1" value="${vehicle.door_height_mm ?? vehicle.interior_height_mm ?? 2500}"></td>
    <td><span class="version-badge">v${vehicle.version ?? 'nouvelle'}</span></td>
    <td><button class="row-delete vehicle-delete" title="Supprimer">×</button></td>`;
  tr.querySelector('.vehicle-delete').addEventListener('click', async () => {
    const modelId = tr.querySelector('[data-v="model_id"]').value.trim();
    if (!exists) { tr.remove(); return; }
    if (!confirm(`Supprimer le véhicule ${modelId} ?`)) return;
    const response = await fetch(`/api/vehicles/${encodeURIComponent(modelId)}`, {method:'DELETE', headers:{'X-Tenant-ID':'demo'}});
    if (!response.ok) { const body=await response.json(); return showVehicleMessage(body.detail || 'Suppression impossible', true); }
    await loadVehicles(); showVehicleMessage('Véhicule supprimé.');
  });
  return tr;
}
function renderVehicleRows() {
  const tbody = $('#vehicle-table tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  state.vehicles.forEach(vehicle => tbody.append(vehicleRowTemplate(vehicle)));
}
function vehicleRowData(row) {
  const original = JSON.parse(row.dataset.original || '{}');
  const payload = {...original};
  row.querySelectorAll('[data-v]').forEach(input => {
    payload[input.dataset.v] = input.type === 'number' ? Number(input.value) : input.value.trim();
  });
  return payload;
}
function showVehicleMessage(message, error=false) {
  const box=$('#vehicle-message'); box.textContent=message; box.classList.toggle('hidden',!message);
  box.classList.toggle('error',error); box.classList.toggle('success',!error);
}
function refreshVehicleSelect(preferred) {
  const select=$('#vehicle-id'); if(!select)return;
  const selected=preferred || select.value || state.vehicles[0]?.model_id;
  select.innerHTML=state.vehicles.map(v=>`<option value="${v.model_id}" ${v.model_id===selected?'selected':''}>${v.name}</option>`).join('');
  if (!select.value && state.vehicles.length) select.value=state.vehicles[0].model_id;
  window.PLO_VEHICLES=state.vehicles;
  updateSelectedVehicleSummary();
}
function updateSelectedVehicleSummary(){
  const vehicle=state.vehicles.find(v=>v.model_id===$('#vehicle-id')?.value);
  const box=$('#selected-vehicle-summary'); if(!box)return;
  box.innerHTML=vehicle ? `<strong>${vehicle.name}</strong><span>${fmt(vehicle.interior_length_mm/1000,2)} × ${fmt(vehicle.interior_width_mm/1000,2)} × ${fmt(vehicle.interior_height_mm/1000,2)} m intérieurs · charge utile ${fmt(vehicle.payload_kg,0)} kg · version ${vehicle.version}</span>` : '';
}
async function loadVehicles(){
  const response=await fetch('/api/vehicles',{headers:{'X-Tenant-ID':'demo'}});
  if(!response.ok)throw new Error('Impossible de charger le catalogue véhicules.');
  const preferred=$('#vehicle-id')?.value;
  state.vehicles=await response.json(); renderVehicleRows(); refreshVehicleSelect(preferred);
}
$('#add-vehicle').addEventListener('click',()=>$('#vehicle-table tbody').append(vehicleRowTemplate()));
$('#save-vehicles').addEventListener('click',async()=>{
  showVehicleMessage('');
  try{
    const rows=$$('#vehicle-table tbody tr');
    if(!rows.length)throw new Error('Ajoutez au moins un véhicule.');
    for(const row of rows){
      const payload=vehicleRowData(row);
      const response=await fetch('/api/vehicles',{method:'POST',headers:{'Content-Type':'application/json','X-Tenant-ID':'demo'},body:JSON.stringify(payload)});
      const body=await response.json();
      if(!response.ok)throw new Error(body.detail?.message || body.detail || `Erreur sur ${payload.model_id}`);
    }
    await loadVehicles(); showVehicleMessage('Catalogue enregistré. Les nouvelles dimensions seront utilisées au prochain calcul.');
  }catch(error){showVehicleMessage(error.message||String(error),true);}
});
$('#reset-vehicles').addEventListener('click',async()=>{
  if(!confirm('Restaurer les deux véhicules de démonstration et supprimer les véhicules personnalisés ?'))return;
  const response=await fetch('/api/vehicles/reset-defaults',{method:'POST',headers:{'X-Tenant-ID':'demo'}});
  if(!response.ok)return showVehicleMessage('Restauration impossible.',true);
  state.vehicles=await response.json();renderVehicleRows();refreshVehicleSelect();showVehicleMessage('Modèles de démonstration restaurés.');
});
$('#vehicle-id').addEventListener('change',updateSelectedVehicleSummary);
renderVehicleRows(); refreshVehicleSelect();

function rowTemplate(item = {}) {
  const tr = document.createElement('tr');
  const order = item.delivery_order ?? ($('#cargo-table tbody').children.length + 1);
  tr.draggable = true;
  tr.innerHTML = `
    <td class="drag-handle" title="Glisser pour réordonner">⋮⋮</td>
    <td><input data-k="id" value="${item.id ?? `PAL-${String(order).padStart(3,'0')}`}"></td>
    <td><input data-k="quantity" type="number" min="1" value="${item.quantity ?? 1}"></td>
    <td><select data-k="shape">${['pallet','box','roll','cylinder','sheet','post','bar_rect','bar_cyl'].map(v => `<option ${item.shape===v?'selected':''}>${v}</option>`).join('')}</select></td>
    <td><input data-k="length" type="number" min="1" value="${item.length ?? 1200}"></td>
    <td><input data-k="width" type="number" min="1" value="${item.width ?? 800}"></td>
    <td><input data-k="height" type="number" min="1" value="${item.height ?? 1200}"></td>
    <td><input data-k="weight" type="number" min="0.1" step="0.1" value="${item.weight ?? 500}"></td>
    <td><input data-k="destination" value="${item.destination ?? `Client ${order}`}"></td>
    <td class="total-route-column"><div class="total-row-address"><input data-total="pickup_address" value="${item.pickup_address ?? ''}" placeholder="Adresse d’enlèvement"><button type="button" class="secondary small total-locate" data-total-location="pickup">Localiser</button></div></td>
    <td class="total-route-column"><div class="total-row-address"><input data-total="delivery_address" value="${item.delivery_address ?? ''}" placeholder="Adresse de livraison"><button type="button" class="secondary small total-locate" data-total-location="delivery">Localiser</button></div></td>
    <td class="total-route-column"><span class="total-row-status">À localiser</span></td>
    <td><input data-k="delivery_order" type="number" min="0" value="${order}"></td>
    <td><input data-k="rotation_allowed" type="checkbox" ${item.rotation_allowed === false || ['non','false','0'].includes(String(item.rotation_allowed).toLowerCase()) ? '' : 'checked'}></td>
    <td><input data-k="keep_together_group" value="${item.keep_together_group ?? ''}" placeholder="G1"></td>
    <td><input data-k="separate_group" value="${item.separate_group ?? ''}" placeholder="S1"></td>
    <td><input data-k="compatibility_tags" value="${Array.isArray(item.compatibility_tags)?item.compatibility_tags.join(','):item.compatibility_tags ?? ''}" placeholder="alimentaire"></td>
    <td><input data-k="incompatible_tags" value="${Array.isArray(item.incompatible_tags)?item.incompatible_tags.join(','):item.incompatible_tags ?? ''}" placeholder="chimique"></td>
    <td><input data-k="separation" type="number" min="0" value="${item.separation ?? 0}"></td>
    <td><button class="row-delete" title="Supprimer">×</button></td>`;
  tr.querySelector('.row-delete').addEventListener('click', () => tr.remove());
  tr.addEventListener('dragstart', () => tr.classList.add('dragging'));
  tr.addEventListener('dragend', () => { tr.classList.remove('dragging'); renumberDefaultOrders(); });
  return tr;
}
function addRow(item) { const row=rowTemplate(item); $('#cargo-table tbody').append(row); return row; }
$('#cargo-table tbody').addEventListener('dragover', event => {
  event.preventDefault();
  const dragging = $('#cargo-table tbody tr.dragging'); if (!dragging) return;
  const siblings = $$('#cargo-table tbody tr:not(.dragging)');
  const next = siblings.find(row => event.clientY <= row.getBoundingClientRect().top + row.offsetHeight / 2);
  $('#cargo-table tbody').insertBefore(dragging, next || null);
});
function renumberDefaultOrders(){ $$('#cargo-table tbody tr').forEach((row,index)=>{ const input=row.querySelector('[data-k="delivery_order"]'); if(input && !input.dataset.manual) input.value=index+1; }); }
$('#cargo-table tbody').addEventListener('input', event => { if(event.target.matches('[data-k="delivery_order"]')) event.target.dataset.manual='1'; });
addRow({id:'PAL-001',destination:'Client A',delivery_order:1});
addRow({id:'PAL-002',destination:'Client B',delivery_order:2,width:1000,weight:600});
$('#add-row').addEventListener('click', () => addRow());
$('#duplicate-row').addEventListener('click', () => {
  const last = $('#cargo-table tbody tr:last-child');
  if (!last) return addRow();
  const item = rowData(last); item.id = `${item.id}-COPY`;
  const copy=addRow(item);
  ['pickup','delivery'].forEach(type=>{
    const source=last.querySelector(`[data-total="${type}_address"]`);
    const target=copy.querySelector(`[data-total="${type}_address"]`);
    if(source&&target)target.value=source.value;
    const prefix=`total${type[0].toUpperCase()}${type.slice(1)}`;
    ['Lat','Lon','Label'].forEach(suffix=>{if(last.dataset[`${prefix}${suffix}`]!=null)copy.dataset[`${prefix}${suffix}`]=last.dataset[`${prefix}${suffix}`];});
  });
});
function rowData(row) {
  const item = {};
  row.querySelectorAll('[data-k]').forEach(input => {
    const k = input.dataset.k;
    item[k] = input.type === 'checkbox' ? input.checked : (input.type === 'number' ? Number(input.value) : input.value.trim());
  });
  return item;
}
const DECISION_STORAGE_KEY = 'axioload.decisions.v1';
const CONNECTION_STORAGE_KEY = 'axioload.connections.v1';
const CONNECTION_SESSION_KEY = 'axioload.connection.session.v1';

function readStorage(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
  } catch (_) {
    return fallback;
  }
}
function writeStorage(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* stockage indisponible dans ce contexte */ } }
let decisionStore = readStorage(DECISION_STORAGE_KEY, {});
let connectionStore = readStorage(CONNECTION_STORAGE_KEY, []);

function persistDecisionStore() { writeStorage(DECISION_STORAGE_KEY, decisionStore); }
function persistConnectionStore() { writeStorage(CONNECTION_STORAGE_KEY, connectionStore); }
function currentUserName() { return appSettings.account?.username || 'Utilisateur local'; }
function isoNow() { return new Date().toISOString(); }
function formatDateTime(value) { return value ? new Date(value).toLocaleString('fr-FR') : '—'; }
function formatDate(value) { return value ? new Date(value).toLocaleDateString('fr-FR') : '—'; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
let connectionTrackedInMemory=false;
function trackConnection() {
  try {
    if (sessionStorage.getItem(CONNECTION_SESSION_KEY)) return;
    sessionStorage.setItem(CONNECTION_SESSION_KEY, '1');
  } catch (_) {
    if (connectionTrackedInMemory) return;
    connectionTrackedInMemory=true;
  }
  connectionStore.push({ timestamp: isoNow(), user: currentUserName() });
  persistConnectionStore();
}
trackConnection();

function buildItemMetaMap(request) {
  const map = {};
  (request?.items || []).forEach(item => {
    const quantity = Math.max(1, Number(item.quantity) || 1);
    for (let index = 0; index < quantity; index += 1) {
      const itemId = quantity === 1 ? item.id : `${item.id}#${index + 1}`;
      map[itemId] = { ...item };
    }
  });
  return map;
}
function syncItemMeta() { state.itemMeta = buildItemMetaMap(state.currentRequest || { items: [] }); }
function placementMeta(itemId) { return state.itemMeta[itemId] || {}; }
function placementShape(placement) { return placementMeta(placement.item_id).shape || 'box'; }
function placementVisualType(placement) {
  const shape = placementShape(placement);
  if (shape === 'pallet') return placement.actual_height_mm <= 180 ? 'pallet_empty' : 'pallet_loaded';
  if (shape === 'box' || shape === 'sheet' || shape === 'post' || shape === 'bar_rect') return 'box';
  if (shape === 'roll' || shape === 'cylinder' || shape === 'bar_cyl') return 'cylinder';
  return 'box';
}
function caseLabelFromRequest(request, fallback = 'Cas sans nom') {
  const ids = (request?.items || []).map(item => item.id).filter(Boolean);
  if (!ids.length) return fallback;
  return ids.length <= 2 ? ids.join(' · ') : `${ids.slice(0, 2).join(' · ')} +${ids.length - 2}`;
}
function typeLabelFromRequest(request) {
  const vehicle = request?.vehicle_policy?.forced_vehicle_id || 'véhicule libre';
  const shapes = [...new Set((request?.items || []).map(item => item.shape).filter(Boolean))];
  return `${vehicle}${shapes.length ? ` · ${shapes.join(', ')}` : ''}`;
}
function statusMeta(status) {
  if (status === 'validated') return { label: 'Validé', className: 'status-validated' };
  if (status === 'failed') return { label: 'Échec', className: 'status-failed' };
  return { label: 'Non enregistré', className: 'status-pending' };
}
function statusBadgeHtml(status) {
  const meta = statusMeta(status);
  return `<span class="status-badge ${meta.className}">${meta.label}</span>`;
}
function getRunDecision(runId) {
  return decisionStore[runId] || { status: 'pending', selectedSolution: null, user: '', decisionAt: '', reason: '', comment: '' };
}
function buildPayload() {
  return {
    dimension_unit: 'mm',
    weight_unit: 'kg',
    seed: Number($('#seed').value),
    default_margins: {
      left: Number($('#default-margin').value),
      right: Number($('#default-margin').value),
      front: Number($('#default-margin').value),
      rear: Number($('#default-margin').value),
      top: 0,
    },
    budget_seconds: Number($('#budget-seconds').value),
    requested_solutions: 5,
    vehicle_policy: { mode: 'forced', forced_vehicle_id: $('#vehicle-id').value, max_vehicles: Number($('#max-vehicles').value) },
    items: $$('#cargo-table tbody tr').map(rowData),
  };
}
function showError(message) {
  const box = $('#data-errors');
  box.textContent = message;
  box.classList.toggle('hidden', !message);
}
function fmt(value, digits = 2) {
  return Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
function planMetricsFromPlacements(plan) {
  const occupiedMm = Math.max(0, ...(plan.placements || []).map(p => p.y_mm + p.envelope_length_mm));
  const occupiedM = occupiedMm / 1000;
  return { occupiedMm, occupiedM, linearMeters: occupiedM };
}
function solutionConsistencyDiagnostics(solution) {
  const diagnostics = [];
  let occupiedTotal = 0;
  let linearTotal = 0;
  solution.vehicle_plans.forEach((plan, index) => {
    const calculated = planMetricsFromPlacements(plan);
    occupiedTotal += calculated.occupiedM;
    linearTotal += calculated.linearMeters;
    if (Math.abs(Number(plan.occupied_length_m) - calculated.occupiedM) > 1e-6 || Math.abs(Number(plan.linear_meters) - calculated.linearMeters) > 1e-6) {
      diagnostics.push({ severity: 'error', code: 'METRIC_DATA_MISMATCH', message: `Le véhicule ${index + 1} présente une incohérence entre ses positions et les métriques affichées.` });
    }
  });
  if (Math.abs(Number(solution.occupied_length_m) - occupiedTotal) > 1e-6 || Math.abs(Number(solution.total_linear_meters) - linearTotal) > 1e-6) {
    diagnostics.push({ severity: 'error', code: 'SOLUTION_METRIC_MISMATCH', message: 'Les totaux de la solution ne correspondent pas à la somme des plans véhicules.' });
  }
  return diagnostics;
}

$('#optimize').addEventListener('click', async () => {
  showError('');
  const button = $('#optimize');
  button.disabled = true;
  button.textContent = 'Calcul en cours…';
  state.explicitSolutionSelection = false;
  state.selectedPlacementId = null;
  try {
    const payload = buildPayload();
    state.currentRequest = payload;
    syncItemMeta();
    if (window.AxioTotalOptimization?.enabled()) {
      await window.AxioTotalOptimization.run(payload);
      return;
    }
    const response = await fetch('/local/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    state.result = result;
    state.selected = 0;
    state.selectedVehicle = 0;
    if (!result.solutions?.length) {
      const diagnostics = (result.diagnostics || []).map(d => `${d.message}`).join('\n');
      throw new Error(diagnostics || 'Le moteur n’a retourné aucun plan. Consultez les dimensions du véhicule et les contraintes saisies.');
    }
    renderResults();
    switchTab('results');
    loadHistory(true);
    renderDashboard();
  } catch (error) {
    showError(error.message || String(error));
  } finally {
    button.disabled = false;
    button.textContent = window.AxioTotalOptimization?.enabled() ? 'Lancer l’optimisation totale' : 'Optimiser le chargement';
  }
});

$('#import-file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const data = new FormData();
  data.append('file', file);
  try {
    const response = await fetch(`/api/import/preview?vehicle_id=${encodeURIComponent($('#vehicle-id').value)}`, { method: 'POST', body: data });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail?.message || body.detail || 'Import invalide');
    $('#cargo-table tbody').innerHTML = '';
    body.payload.items.forEach(addRow);
    showError('');
  } catch (error) {
    showError(error.message || String(error));
  }
});

function showDecisionMessage(message, isError = false) {
  const box = $('#decision-message');
  box.textContent = message;
  box.className = `message ${isError ? 'error' : ''}`.trim();
  box.classList.toggle('hidden', !message);
}
function updateExplicitSelection(selectedIndex, userInitiated = true) {
  state.selected = selectedIndex;
  if (userInitiated) state.explicitSolutionSelection = true;
}
function renderDecisionSection() {
  const runId = state.result?.run_id;
  const decision = runId ? getRunDecision(runId) : { status: 'pending' };
  const selectedRank = state.result?.solutions?.[state.selected]?.rank;
  const statusEl = $('#decision-status');
  if (decision.status === 'validated') {
    statusEl.innerHTML = `${statusBadgeHtml('validated')} <strong>Solution ${state.result.solutions[decision.selectedSolution]?.rank ?? selectedRank}</strong> enregistrée le ${formatDateTime(decision.decisionAt)} par ${escapeHtml(decision.user || 'Utilisateur local')}.`;
  } else if (decision.status === 'failed') {
    const extra = [decision.reason, decision.comment].filter(Boolean).join(' · ');
    statusEl.innerHTML = `${statusBadgeHtml('failed')} cas déclaré en échec le ${formatDateTime(decision.decisionAt)} par ${escapeHtml(decision.user || 'Utilisateur local')}${extra ? ` · ${escapeHtml(extra)}` : ''}.`;
  } else {
    statusEl.innerHTML = `${statusBadgeHtml('pending')} aucune décision finale n’a encore été enregistrée pour ce cas.`;
  }
  $('#failure-reason').value = decision.reason || '';
  $('#failure-comment').value = decision.comment || '';
  $('#validate-optimization').disabled = !state.result || !(state.explicitSolutionSelection || decision.status === 'validated');
  $('#declare-failure').disabled = !state.result;
}
async function saveDecision(decision) {
  if (!state.result?.run_id) return;
  decisionStore[state.result.run_id] = { ...getRunDecision(state.result.run_id), ...decision };
  persistDecisionStore();
  await loadHistory(true);
  renderDashboard();
  renderResults();
}
$('#validate-optimization').addEventListener('click', async () => {
  if (!state.result || !state.result.solutions?.length) return;
  if (!(state.explicitSolutionSelection || getRunDecision(state.result.run_id).status === 'validated')) return;
  const solution = state.result.solutions[state.selected];
  if (!confirm(`Valider la solution ${solution.rank} pour ce cas ?`)) return;
  await saveDecision({
    status: 'validated',
    selectedSolution: state.selected,
    decisionAt: isoNow(),
    user: currentUserName(),
    reason: '',
    comment: $('#failure-comment').value.trim(),
  });
  showDecisionMessage(`Solution ${solution.rank} validée avec succès.`);
});
$('#declare-failure').addEventListener('click', async () => {
  if (!state.result) return;
  const reason = $('#failure-reason').value;
  const comment = $('#failure-comment').value.trim();
  if (!confirm('Confirmer la déclaration d’échec pour ce cas ?')) return;
  await saveDecision({
    status: 'failed',
    selectedSolution: null,
    decisionAt: isoNow(),
    user: currentUserName(),
    reason,
    comment,
  });
  showDecisionMessage('Le cas a été enregistré avec le statut « Échec ».', true);
});

function renderResults() {
  if (!state.result?.solutions?.length) return;
  $('#empty-results').classList.add('hidden');
  $('#results-content').classList.remove('hidden');
  $('#run-meta').textContent = `${state.result.status} · ${fmt(state.result.elapsed_seconds, 3)} s · graine ${state.result.seed}`;
  const cards = $('#solution-cards');
  cards.innerHTML = '';
  const decision = getRunDecision(state.result.run_id);
  state.result.solutions.forEach((solution, index) => {
    const isViewed = index === state.selected;
    const isDecisionSelection = decision.status === 'validated' && decision.selectedSolution === index;
    const card = document.createElement('article');
    card.className = `solution-card ${index === 0 ? 'recommended' : ''} ${isViewed ? 'active' : ''} ${isDecisionSelection ? 'decision-selected' : ''}`;
    card.tabIndex = 0;
    card.setAttribute('role','button');
    card.setAttribute('aria-pressed',String(isViewed));
    const methodName=solution.method_name||'Méthode historique';
    const methodDescription=solution.method_description||'Méthode utilisée lors de la génération de cette solution.';
    card.innerHTML = `
      <div class="solution-card-top">
        <span class="solution-radio ${isViewed ? 'is-selected' : ''}" aria-hidden="true"></span>
        <span class="solution-card-title">Solution ${solution.rank}</span>
        ${isDecisionSelection ? '<span class="inline-badge">Solution sélectionnée</span>' : ''}
      </div>
      <div class="solution-method"><span>Mode de calcul</span><strong>${escapeHtml(methodName)}</strong><button type="button" class="help-tip small-tip method-help" data-tooltip="${escapeHtml(methodDescription)}" aria-label="Définition de la méthode ${escapeHtml(methodName)}">?</button></div>
      <div class="metric-big">${fmt(solution.total_linear_meters)} <span>m.l.</span></div>
      <div class="metric-row"><span>Véhicules</span><strong>${solution.vehicle_count}</strong></div>
      <div class="metric-row"><span>Longueur réellement occupée</span><strong>${fmt(solution.occupied_length_m)} m</strong></div>
    `;
    const selectCard=()=>{
      updateExplicitSelection(index, true);
      state.selectedVehicle = 0;
      state.selectedPlacementId = null;
      renderResults();
    };
    card.addEventListener('click',event=>{if(!event.target.closest('.method-help'))selectCard();});
    card.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&!event.target.closest('.method-help')){event.preventDefault();selectCard();}});
    cards.append(card);
    bindHelpTips(card);
  });
  const solution = state.result.solutions[state.selected];
  if (state.selectedVehicle >= solution.vehicle_plans.length) state.selectedVehicle = 0;
  const vehicleSelect = $('#viewer-vehicle');
  vehicleSelect.innerHTML = solution.vehicle_plans.map((plan, index) => `<option value="${index}" ${index === state.selectedVehicle ? 'selected' : ''}>Véhicule ${index + 1}</option>`).join('');
  vehicleSelect.classList.toggle('hidden', solution.vehicle_plans.length === 1);
  const plan = solution.vehicle_plans[state.selectedVehicle];
  const vehicle = vehicleFor(plan);
  const metrics = planMetricsFromPlacements(plan);
  $('#viewer-title').textContent = `Solution ${solution.rank} · ${solution.method_name || 'Méthode historique'} · ${plan.vehicle_name}`;
  $('#viewer-subtitle').textContent = `Longueur occupée ${fmt(metrics.occupiedM)} m · ${fmt(metrics.linearMeters)} m.l. · véhicule ${fmt(vehicle.interior_length_mm / 1000)} × ${fmt(vehicle.interior_width_mm / 1000)} × ${fmt(vehicle.interior_height_mm / 1000)} m`;
  const diagnostics = [
    ...(state.result.diagnostics || []),
    ...(solution.diagnostics || []),
    ...solutionConsistencyDiagnostics(solution),
  ];
  $('#diagnostics').innerHTML = diagnostics.length
    ? diagnostics.map(d => `<div class="diag ${d.severity === 'error' ? 'diag-error' : ''}"><strong>${escapeHtml(d.code || 'INFO')}</strong><span>${escapeHtml(d.message)}</span></div>`).join('')
    : '<div class="diag"><strong>OK</strong><span>Aucun diagnostic bloquant sur la solution affichée.</span></div>';
  $('#exports').innerHTML = `<a href="/api/history/${state.result.run_id}/export.csv">CSV placements</a><a href="/api/history/${state.result.run_id}/export.xlsx">XLSX placements</a><a href="/api/history/${state.result.run_id}/export.json">JSON complet</a><a href="#" id="export-operational-pdf">PDF opérationnel avec vue 3D</a>`;
  $('#export-operational-pdf').addEventListener('click', exportOperationalPdf);
  renderDecisionSection();
  renderInspectionCard(null);
  drawViewer();
}

function vehicleFor(plan) {
  const modelId = String(plan.vehicle_version_id || '').split('@')[0] || String(plan.vehicle_model_id || '');
  return state.vehicles.find(v => v.model_id === modelId) || {
    model_id: modelId,
    name: plan.vehicle_name || 'Véhicule',
    interior_length_mm: 13600,
    interior_width_mm: 2450,
    interior_height_mm: 2700,
    obstacles: [],
  };
}
function paletteColor(index) {
  const colors = ['#2CB8BA', '#4F8AC6', '#A0D26F', '#E99454', '#9775D4', '#F0C25B', '#58C2E6'];
  return colors[index % colors.length];
}
function sceneColors() {
  const dark = document.documentElement.dataset.theme === 'dark';
  return dark ? {
    background: '#071D27', floor: 'rgba(24,72,92,.82)', floorStroke: '#7BC8D6', frame: 'rgba(117,176,191,.75)',
    topFrame: 'rgba(117,176,191,.55)', grid: 'rgba(38,117,140,.32)', labelBackground: 'rgba(7,25,37,.92)',
    labelColor: '#F5FAFC', labelBorder: '#7BC8D6', metricBackground: 'rgba(5,47,74,.92)', outline: '#08161D',
  } : {
    background: '#F4FBFD', floor: 'rgba(197,231,237,.95)', floorStroke: '#0C6C89', frame: 'rgba(31,113,137,.55)',
    topFrame: 'rgba(31,113,137,.38)', grid: 'rgba(31,113,137,.18)', labelBackground: 'rgba(255,255,255,.96)',
    labelColor: '#08384A', labelBorder: '#0C6C89', metricBackground: 'rgba(7,60,91,.9)', outline: '#17303B',
  };
}
function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  const r = n >> 16;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}
function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, (n >> 16) + amount));
  const g = Math.max(0, Math.min(255, ((n >> 8) & 255) + amount));
  const b = Math.max(0, Math.min(255, (n & 255) + amount));
  return `#${[r, g, b].map(value => value.toString(16).padStart(2, '0')).join('')}`;
}
function line(target, a, b, color, width = 1, dash = []) {
  target.save();
  target.beginPath();
  target.setLineDash(dash);
  target.moveTo(a[0], a[1]);
  target.lineTo(b[0], b[1]);
  target.strokeStyle = color;
  target.lineWidth = width;
  target.stroke();
  target.restore();
}
function polygon(target, points, fill, stroke = null, width = 1) {
  if (!points.length) return;
  target.beginPath();
  target.moveTo(points[0][0], points[0][1]);
  points.slice(1).forEach(point => target.lineTo(point[0], point[1]));
  target.closePath();
  if (fill) {
    target.fillStyle = fill;
    target.fill();
  }
  if (stroke) {
    target.strokeStyle = stroke;
    target.lineWidth = width;
    target.stroke();
  }
}
function screenLabel(target, text, x, y, options = {}) {
  const { font = '800 11px Segoe UI, Arial, sans-serif', background = 'rgba(255,255,255,.95)', color = '#052E46', border = '#0B526C', align = 'center' } = options;
  target.save();
  target.font = font;
  target.textAlign = align;
  target.textBaseline = 'middle';
  const metrics = target.measureText(text);
  const padX = 8;
  const padY = 5;
  const boxWidth = metrics.width + padX * 2;
  const boxHeight = 24;
  const left = align === 'right' ? x - boxWidth : align === 'left' ? x : x - boxWidth / 2;
  const top = y - boxHeight / 2;
  target.fillStyle = background;
  target.strokeStyle = border;
  target.lineWidth = 1.4;
  target.beginPath();
  target.roundRect(left, top, boxWidth, boxHeight, 8);
  target.fill();
  target.stroke();
  target.fillStyle = color;
  target.fillText(text, align === 'right' ? left + boxWidth - padX : align === 'left' ? left + padX : x, y + 0.5);
  target.restore();
}
// coordinate contract preserved: projectWorld(longitudinal,width,height,origin,scale,view)
// Position longitudinale = axe Y du véhicule, largeur = axe X, hauteur = axe Z
function projectWorld(longitudinal, transverse, vertical, origin, scale, view) {
  const ang = view.angle;
  const c = Math.cos(ang);
  const s = Math.sin(ang);
  const lx = longitudinal * c - transverse * s;
  const ly = longitudinal * s + transverse * c;
  return [
    origin[0] + view.panX + lx * scale,
    origin[1] + view.panY + ly * scale * 0.42 - vertical * scale * view.tilt,
  ];
}
function drawGrid(target, vehicle, origin, scale, view, scene) {
  const step = 1000;
  for (let x = step; x < vehicle.interior_length_mm; x += step) {
    line(target, projectWorld(x, 0, 0, origin, scale, view), projectWorld(x, vehicle.interior_width_mm, 0, origin, scale, view), scene.grid, 1, [6, 6]);
  }
  for (let y = step; y < vehicle.interior_width_mm; y += step) {
    line(target, projectWorld(0, y, 0, origin, scale, view), projectWorld(vehicle.interior_length_mm, y, 0, origin, scale, view), scene.grid, 1, [6, 6]);
  }
}
function drawDimension(target, from, to, label, color, origin, scale, view) {
  const a = projectWorld(...from, origin, scale, view);
  const b = projectWorld(...to, origin, scale, view);
  line(target, a, b, color, 2);
  const arrow = 8;
  [[a, b], [b, a]].forEach(([p1, p2]) => {
    const dx = p2[0] - p1[0];
    const dy = p2[1] - p1[1];
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const left = [p1[0] + ux * arrow - uy * arrow * 0.6, p1[1] + uy * arrow + ux * arrow * 0.6];
    const right = [p1[0] + ux * arrow + uy * arrow * 0.6, p1[1] + uy * arrow - ux * arrow * 0.6];
    line(target, p1, left, color, 2);
    line(target, p1, right, color, 2);
  });
  screenLabel(target, label, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 12, { background: hexToRgba(color, 0.12), color, border: color, font: '800 12px Segoe UI, Arial, sans-serif' });
}
function cuboidPoints(longitudinal, transverse, width, length, zBase, height, origin, scale, view) {
  return {
    A: projectWorld(longitudinal, transverse, zBase, origin, scale, view),
    B: projectWorld(longitudinal + length, transverse, zBase, origin, scale, view),
    C: projectWorld(longitudinal + length, transverse + width, zBase, origin, scale, view),
    D: projectWorld(longitudinal, transverse + width, zBase, origin, scale, view),
    E: projectWorld(longitudinal, transverse, zBase + height, origin, scale, view),
    F: projectWorld(longitudinal + length, transverse, zBase + height, origin, scale, view),
    G: projectWorld(longitudinal + length, transverse + width, zBase + height, origin, scale, view),
    H: projectWorld(longitudinal, transverse + width, zBase + height, origin, scale, view),
  };
}
function addHitArea(points, placement) {
  const all = Object.values(points);
  const xs = all.map(p => p[0]);
  const ys = all.map(p => p[1]);
  state.hitAreas.push({ minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys), placement });
}
function isSelectedPlacement(placement) { return state.selectedPlacementId && state.selectedPlacementId === placement.item_id; }
function drawCuboid(target, placement, color, origin, scale, view, options = {}) {
  const { zBase = placement.z_mm || 0, height = placement.actual_height_mm, width = placement.envelope_width_mm, length = placement.envelope_length_mm, label = true } = options;
  const points = cuboidPoints(placement.y_mm, placement.x_mm, width, length, zBase, height, origin, scale, view);
  const selected = isSelectedPlacement(placement);
  const outline = selected ? '#FF4B5C' : '#08161D';
  const strokeWidth = selected ? 2.8 : 1.7;
  polygon(target, [points.A, points.B, points.F, points.E], hexToRgba(shade(color, -12), 0.88), outline, strokeWidth);
  polygon(target, [points.B, points.C, points.G, points.F], hexToRgba(shade(color, -26), 0.92), outline, strokeWidth);
  polygon(target, [points.E, points.F, points.G, points.H], hexToRgba(color, 0.82), outline, strokeWidth);
  line(target, points.A, points.D, outline, strokeWidth);
  line(target, points.D, points.H, outline, strokeWidth);
  line(target, points.C, points.D, outline, strokeWidth);
  if (label) {
    const topCenter = projectWorld(placement.y_mm + length / 2, placement.x_mm + width / 2, zBase + height, origin, scale, view);
    screenLabel(target, placement.item_id, topCenter[0], topCenter[1] - 8, { background: selected ? 'rgba(255,244,246,.97)' : sceneColors().labelBackground, color: selected ? '#A3162B' : sceneColors().labelColor, border: selected ? '#FF4B5C' : sceneColors().labelBorder });
  }
  return points;
}
function drawPallet(target, placement, color, origin, scale, view) {
  const selected = isSelectedPlacement(placement);
  const baseHeight = Math.min(150, Math.max(95, Math.round(placement.actual_height_mm * 0.16)));
  const loadHeight = Math.max(0, placement.actual_height_mm - baseHeight);
  const outline = selected ? '#FF4B5C' : '#08161D';
  const wood = '#C18A54';
  const darkWood = '#8D6034';
  const runnerHeight = Math.max(35, Math.round(baseHeight * 0.35));
  const deckHeight = Math.max(22, Math.round(baseHeight * 0.28));
  const deckBase = runnerHeight;
  const runnerWidth = placement.envelope_width_mm / 5.2;
  const runnerOffsets = [0, (placement.envelope_width_mm - runnerWidth) / 2, placement.envelope_width_mm - runnerWidth];
  runnerOffsets.forEach(offset => {
    drawCuboid(target, { ...placement, x_mm: placement.x_mm + offset, envelope_width_mm: runnerWidth, actual_height_mm: runnerHeight }, darkWood, origin, scale, view, { zBase: placement.z_mm || 0, height: runnerHeight, width: runnerWidth, length: placement.envelope_length_mm, label: false });
  });
  drawCuboid(target, { ...placement, actual_height_mm: deckHeight }, wood, origin, scale, view, { zBase: deckBase, height: deckHeight, width: placement.envelope_width_mm, length: placement.envelope_length_mm, label: false });
  const deckPoints = cuboidPoints(placement.y_mm, placement.x_mm, placement.envelope_width_mm, placement.envelope_length_mm, deckBase, deckHeight, origin, scale, view);
  for (let i = 1; i <= 4; i += 1) {
    const y = placement.y_mm + (placement.envelope_length_mm / 5) * i;
    line(target, projectWorld(y, placement.x_mm, deckBase + deckHeight, origin, scale, view), projectWorld(y, placement.x_mm + placement.envelope_width_mm, deckBase + deckHeight, origin, scale, view), outline, 1.1);
  }
  if (loadHeight > 26) {
    const inset = Math.min(25, Math.round(Math.min(placement.envelope_length_mm, placement.envelope_width_mm) * 0.02));
    drawCuboid(target, {
      ...placement,
      y_mm: placement.y_mm + inset,
      x_mm: placement.x_mm + inset,
      envelope_length_mm: Math.max(placement.envelope_length_mm - inset * 2, placement.envelope_length_mm * 0.85),
      envelope_width_mm: Math.max(placement.envelope_width_mm - inset * 2, placement.envelope_width_mm * 0.85),
      actual_height_mm: loadHeight,
    }, color, origin, scale, view, { zBase: deckBase + deckHeight, height: loadHeight, width: Math.max(placement.envelope_width_mm - inset * 2, placement.envelope_width_mm * 0.85), length: Math.max(placement.envelope_length_mm - inset * 2, placement.envelope_length_mm * 0.85), label: false });
  }
  const points = cuboidPoints(placement.y_mm, placement.x_mm, placement.envelope_width_mm, placement.envelope_length_mm, 0, placement.actual_height_mm, origin, scale, view);
  if (selected) {
    polygon(target, [points.E, points.F, points.G, points.H], 'rgba(255,75,92,.08)', '#FF4B5C', 2.4);
  }
  const topCenter = projectWorld(placement.y_mm + placement.envelope_length_mm / 2, placement.x_mm + placement.envelope_width_mm / 2, placement.actual_height_mm, origin, scale, view);
  screenLabel(target, placement.item_id, topCenter[0], topCenter[1] - 8, { background: selected ? 'rgba(255,244,246,.97)' : sceneColors().labelBackground, color: selected ? '#A3162B' : sceneColors().labelColor, border: selected ? '#FF4B5C' : sceneColors().labelBorder });
  return points;
}
function drawCylinder(target, placement, color, origin, scale, view) {
  const selected = isSelectedPlacement(placement);
  const outline = selected ? '#FF4B5C' : '#08161D';
  const length = placement.envelope_length_mm;
  const width = placement.envelope_width_mm;
  const height = placement.actual_height_mm;
  const front = projectWorld(placement.y_mm, placement.x_mm + width / 2, 0, origin, scale, view);
  const back = projectWorld(placement.y_mm + length, placement.x_mm + width / 2, 0, origin, scale, view);
  const topFront = projectWorld(placement.y_mm, placement.x_mm + width / 2, height, origin, scale, view);
  const topBack = projectWorld(placement.y_mm + length, placement.x_mm + width / 2, height, origin, scale, view);
  const radiusX = Math.max(12, Math.abs(projectWorld(placement.y_mm, placement.x_mm + width, 0, origin, scale, view)[0] - front[0]));
  const radiusY = Math.max(8, radiusX * 0.36);
  target.save();
  target.fillStyle = hexToRgba(color, 0.82);
  target.strokeStyle = outline;
  target.lineWidth = selected ? 2.7 : 1.6;
  target.beginPath();
  target.ellipse(topFront[0], topFront[1], radiusX, radiusY, 0, Math.PI, 0, true);
  target.lineTo(topBack[0] + radiusX, topBack[1]);
  target.ellipse(topBack[0], topBack[1], radiusX, radiusY, 0, 0, Math.PI, true);
  target.lineTo(topFront[0] - radiusX, topFront[1]);
  target.fill();
  target.stroke();
  line(target, [front[0] - radiusX, front[1]], [topFront[0] - radiusX, topFront[1]], outline, target.lineWidth);
  line(target, [front[0] + radiusX, front[1]], [topFront[0] + radiusX, topFront[1]], outline, target.lineWidth);
  line(target, [back[0] - radiusX, back[1]], [topBack[0] - radiusX, topBack[1]], outline, target.lineWidth);
  line(target, [back[0] + radiusX, back[1]], [topBack[0] + radiusX, topBack[1]], outline, target.lineWidth);
  screenLabel(target, placement.item_id, topBack[0], topBack[1] - 10, { background: selected ? 'rgba(255,244,246,.97)' : sceneColors().labelBackground, color: selected ? '#A3162B' : sceneColors().labelColor, border: selected ? '#FF4B5C' : sceneColors().labelBorder });
  target.restore();
  const points = cuboidPoints(placement.y_mm, placement.x_mm, placement.envelope_width_mm, placement.envelope_length_mm, 0, placement.actual_height_mm, origin, scale, view);
  return points;
}
function drawObject(target, placement, color, origin, scale, view, interactive) {
  const visualType = placementVisualType(placement);
  let points;
  if (visualType === 'pallet_empty' || visualType === 'pallet_loaded') points = drawPallet(target, placement, color, origin, scale, view);
  else if (visualType === 'cylinder') points = drawCylinder(target, placement, color, origin, scale, view);
  else points = drawCuboid(target, placement, color, origin, scale, view);
  if (interactive) addHitArea(points, placement);
}
function drawScene(target, targetCanvas, { interactive = false, exportMode = false } = {}) {
  if (!state.result?.solutions?.length) return;
  const solution = state.result.solutions[state.selected];
  const plan = solution.vehicle_plans[state.selectedVehicle];
  const vehicle = vehicleFor(plan);
  const scene = sceneColors();
  target.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
  target.fillStyle = scene.background;
  target.fillRect(0, 0, targetCanvas.width, targetCanvas.height);
  if (interactive) state.hitAreas = [];
  const max = Math.max(vehicle.interior_length_mm, vehicle.interior_width_mm, vehicle.interior_height_mm * 1.7);
  const scale = (targetCanvas.width / 1000) * 430 / max * state.zoom;
  const origin = [targetCanvas.width * 0.44, targetCanvas.height * 0.76];
  const L = vehicle.interior_length_mm;
  const W = vehicle.interior_width_mm;
  const H = vehicle.interior_height_mm;
  const floor = [[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]].map(p => projectWorld(...p, origin, scale, state));
  polygon(target, floor, scene.floor, scene.floorStroke, 1.5);
  drawGrid(target, vehicle, origin, scale, state, scene);
  [[[0, 0, 0], [0, 0, H]], [[L, 0, 0], [L, 0, H]], [[L, W, 0], [L, W, H]], [[0, W, 0], [0, W, H]]].forEach(pair => line(target, projectWorld(...pair[0], origin, scale, state), projectWorld(...pair[1], origin, scale, state), scene.frame, 1.3));
  const topFrame = [[0, 0, H], [L, 0, H], [L, W, H], [0, W, H], [0, 0, H]].map(p => projectWorld(...p, origin, scale, state));
  for (let i = 0; i < topFrame.length - 1; i += 1) line(target, topFrame[i], topFrame[i + 1], scene.topFrame, 1.1, [5, 5]);
  (vehicle.obstacles || []).forEach(obstacle => drawCuboid(target, {
    x_mm: obstacle.x_mm, y_mm: obstacle.y_mm, z_mm: 0, envelope_width_mm: obstacle.width_mm, envelope_length_mm: obstacle.length_mm,
    actual_height_mm: obstacle.height_mm, item_id: obstacle.id, destination: 'Obstacle', weight_kg: 0, delivery_order: 0,
  }, '#8B95A1', origin, scale, state, { label: false }));
  const sorted = [...(plan.placements || [])].sort((a, b) => (a.y_mm + a.x_mm) - (b.y_mm + b.x_mm));
  sorted.forEach((placement, index) => drawObject(target, placement, paletteColor(index), origin, scale, state, interactive));
  drawDimension(target, [0, W + 420, 0], [L, W + 420, 0], `Longueur ${fmt(L / 1000)} m`, '#00A8BF', origin, scale, state);
  drawDimension(target, [-280, 0, 0], [-280, W, 0], `Largeur ${fmt(W / 1000)} m`, '#18A999', origin, scale, state);
  drawDimension(target, [0, W + 260, 0], [0, W + 260, H], `Hauteur ${fmt(H / 1000)} m`, '#E83E5B', origin, scale, state);
  const rear = projectWorld(0, W / 2, 0, origin, scale, state);
  screenLabel(target, 'Porte arrière', rear[0], rear[1] + 24, { font: '700 12px Segoe UI, Arial, sans-serif', background: scene.labelBackground, color: scene.labelColor, border: scene.labelBorder });
  const metrics = planMetricsFromPlacements(plan);
  screenLabel(target, `${fmt(metrics.occupiedM)} m occupés · ${fmt(metrics.linearMeters)} m.l.`, targetCanvas.width - 22, 24, { align: 'right', font: exportMode ? '800 18px Segoe UI, Arial, sans-serif' : '800 13px Segoe UI, Arial, sans-serif', background: scene.metricBackground, color: '#FFFFFF', border: '#063B5B' });
}
const canvas = $('#viewer');
const ctx = canvas.getContext('2d');

function drawViewer() { if (state.result) drawScene(ctx, canvas, { interactive: true }); }
function renderSceneDataUrl() {
  const exportCanvas = document.createElement('canvas');
  exportCanvas.width = 1800;
  exportCanvas.height = 1100;
  const exportContext = exportCanvas.getContext('2d');
  drawScene(exportContext, exportCanvas, { interactive: false, exportMode: true });
  return exportCanvas.toDataURL('image/png', 1);
}
async function exportOperationalPdf(event) {
  event.preventDefault();
  const link = event.currentTarget;
  const run = state.result.run_id;
  const solution = state.result.solutions[state.selected];
  link.textContent = 'Préparation du PDF…';
  link.style.pointerEvents = 'none';
  try {
    const plan = solution.vehicle_plans[state.selectedVehicle];
    const vehicle = vehicleFor(plan);
    const metrics = planMetricsFromPlacements(plan);
    const response = await fetch(`/api/history/${run}/export-operational.pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_data_url: renderSceneDataUrl(),
        solution_index: state.selected,
        vehicle_index: state.selectedVehicle,
        displayed_metrics: { occupied_length_m: metrics.occupiedM, linear_meters: metrics.linearMeters },
        vehicle_dimensions: {
          interior_length_mm: vehicle.interior_length_mm,
          interior_width_mm: vehicle.interior_width_mm,
          interior_height_mm: vehicle.interior_height_mm,
        },
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Export opérationnel impossible.');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `axioload-plan-${run}-solution-${solution.rank}.pdf`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    alert(error.message || String(error));
  } finally {
    link.textContent = 'PDF opérationnel avec vue 3D';
    link.style.pointerEvents = '';
  }
}
canvas.addEventListener('pointerdown', event => {
  state.drag = {
    x: event.clientX,
    y: event.clientY,
    angle: state.angle,
    tilt: state.tilt,
    panX: state.panX,
    panY: state.panY,
    moved: false,
    mode: event.shiftKey || event.button === 1 || event.buttons === 4 ? 'pan' : 'orbit',
  };
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
  if (!state.drag) return;
  const dx = event.clientX - state.drag.x;
  const dy = event.clientY - state.drag.y;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) state.drag.moved = true;
  if (state.drag.mode === 'pan') {
    state.panX = state.drag.panX + dx;
    state.panY = state.drag.panY + dy;
  } else {
    state.angle = state.drag.angle + dx * 0.008;
    state.tilt = Math.max(0.18, Math.min(1.15, state.drag.tilt - dy * 0.006));
  }
  drawViewer();
});
canvas.addEventListener('pointerup', event => {
  if (!state.drag?.moved) {
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * canvas.width / rect.width;
    const y = (event.clientY - rect.top) * canvas.height / rect.height;
    const hit = [...state.hitAreas].reverse().find(area => x >= area.minX && x <= area.maxX && y >= area.minY && y <= area.maxY);
    if (hit) {
      state.selectedPlacementId = hit.placement.item_id;
      renderInspectionCard(hit.placement);
      drawViewer();
    }
  }
  state.drag = null;
});
canvas.addEventListener('pointercancel', () => { state.drag = null; });
$('#reset-view').addEventListener('click', () => {
  state.angle = -0.72;
  state.tilt = 0.52;
  state.zoom = 1.45;
  state.panX = 0;
  state.panY = 0;
  drawViewer();
});
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  state.zoom = Math.max(0.65, Math.min(4, state.zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
  drawViewer();
}, { passive: false });
$('#viewer-vehicle').addEventListener('change', event => {
  state.selectedVehicle = Number(event.target.value);
  state.selectedPlacementId = null;
  renderResults();
});
function renderInspectionCard(placement) {
  const container = $('#inspection');
  if (!placement) {
    container.innerHTML = 'Cliquez sur un objet dans la scène.';
    return;
  }
  const meta = placementMeta(placement.item_id);
  const type = placementVisualType(placement) === 'pallet_empty' ? 'Palette vide' : placementVisualType(placement) === 'pallet_loaded' ? 'Palette chargée' : placementVisualType(placement) === 'cylinder' ? 'Objet cylindrique' : 'Box / objet rectangulaire';
  container.innerHTML = `
    <div class="object-card">
      <strong>${escapeHtml(placement.item_id)}</strong>
      <div class="object-type">${escapeHtml(type)}</div>
      <div class="object-detail"><span>Destination</span><strong>${escapeHtml(placement.destination || meta.destination || '—')}</strong></div>
      <div class="object-detail"><span>Position</span><strong>X ${placement.x_mm} mm · Y ${placement.y_mm} mm · Z ${placement.z_mm} mm</strong></div>
      <div class="object-detail"><span>Dimensions</span><strong>${placement.actual_length_mm} × ${placement.actual_width_mm} × ${placement.actual_height_mm} mm</strong></div>
      <div class="object-detail"><span>Poids</span><strong>${fmt(placement.weight_kg, 1)} kg</strong></div>
      <div class="object-detail"><span>Orientation</span><strong>${placement.orientation_deg}°</strong></div>
      <div class="object-detail"><span>Ordre de livraison</span><strong>${placement.delivery_order ?? '—'}</strong></div>
    </div>`;
}

async function fetchRunDetail(id) {
  const response = await fetch(`/api/history/${id}`);
  if (!response.ok) throw new Error('Chargement du calcul impossible.');
  return response.json();
}
function effectiveRunStatus(run) { return run.decision?.status || 'pending'; }
function withinDateRange(value, from, to) {
  if (!value) return false;
  const day = value.slice(0, 10);
  return (!from || day >= from) && (!to || day <= to);
}
async function getHistoryRuns(force = false) {
  if (!force && state.historyCache.length) return state.historyCache;
  const response = await fetch('/api/history');
  if (!response.ok) throw new Error('Impossible de charger l’historique.');
  const runs = await response.json();
  const details = await Promise.all(runs.map(async run => {
    try {
      const detail = await fetchRunDetail(run.id);
      const decision = getRunDecision(run.id);
      return {
        ...run,
        request: detail.request,
        result: detail.result,
        decision,
        caseLabel: caseLabelFromRequest(detail.request, run.id.slice(0, 8)),
        typeLabel: typeLabelFromRequest(detail.request),
      };
    } catch (_) {
      return { ...run, request: null, result: null, decision: getRunDecision(run.id), caseLabel: run.id.slice(0, 8), typeLabel: '—' };
    }
  }));
  state.historyCache = details.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  return state.historyCache;
}
function filterHistoryRuns(runs) {
  const status = $('#history-filter-status').value;
  const user = $('#history-filter-user').value.trim().toLowerCase();
  const type = $('#history-filter-type').value.trim().toLowerCase();
  const caseText = $('#history-filter-case').value.trim().toLowerCase();
  const from = $('#history-filter-from').value;
  const to = $('#history-filter-to').value;
  return runs.filter(run => {
    const runStatus = effectiveRunStatus(run);
    if (status !== 'all' && runStatus !== status) return false;
    if (user && !(run.decision?.user || '').toLowerCase().includes(user)) return false;
    if (type && !`${run.typeLabel || ''} ${run.request?.vehicle_policy?.forced_vehicle_id || ''}`.toLowerCase().includes(type)) return false;
    if (caseText && !`${run.caseLabel || ''} ${run.id}`.toLowerCase().includes(caseText)) return false;
    if ((from || to) && !withinDateRange(run.created_at, from, to)) return false;
    return true;
  });
}
function renderHistoryList() {
  const list = $('#history-list');
  const runs = filterHistoryRuns(state.historyCache);
  list.innerHTML = runs.length ? '' : '<div class="empty-state">Aucun calcul ne correspond aux filtres actuels.</div>';
  runs.forEach(run => {
    const status = effectiveRunStatus(run);
    const reason = run.decision?.reason ? `<div class="history-meta-sub">Motif : ${escapeHtml(run.decision.reason)}</div>` : '';
    const comment = run.decision?.comment ? `<div class="history-meta-sub">Commentaire : ${escapeHtml(run.decision.comment)}</div>` : '';
    const linear = run.linear_meters == null ? '—' : `${fmt(run.linear_meters)} m.l.`;
    const decisionInfo = run.decision?.decisionAt ? `${formatDateTime(run.decision.decisionAt)} · ${escapeHtml(run.decision.user || 'Utilisateur local')}` : 'Aucune décision finale';
    const div = document.createElement('article');
    div.className = 'history-item';
    div.innerHTML = `
      <div class="history-main">
        <div class="history-top-row">
          <strong>${escapeHtml(run.caseLabel)}</strong>
          ${statusBadgeHtml(status)}
        </div>
        <div class="history-meta">ID ${escapeHtml(run.id.slice(0, 8))} · ${formatDateTime(run.created_at)} · ${escapeHtml(run.typeLabel)}</div>
        <div class="history-meta">${run.vehicle_count ?? '—'} véhicule(s) · ${linear} · décision : ${decisionInfo}</div>
        ${reason}
        ${comment}
      </div>
      <div class="history-actions">
        <button data-action="open">Ouvrir</button>
        <button data-action="duplicate">Dupliquer</button>
      </div>`;
    div.querySelector('[data-action="open"]').addEventListener('click', () => openRun(run.id));
    div.querySelector('[data-action="duplicate"]').addEventListener('click', () => duplicateRun(run.id));
    list.append(div);
  });
}
async function loadHistory(force = false) {
  const list = $('#history-list');
  list.innerHTML = 'Chargement…';
  try {
    await getHistoryRuns(force);
    renderHistoryList();
  } catch (error) {
    list.textContent = error.message || String(error);
  }
}
async function openRun(id) {
  const run = await fetchRunDetail(id);
  state.currentRequest = run.request;
  syncItemMeta();
  state.result = { ...run.result, run_id: id };
  const decision = getRunDecision(id);
  state.selected = decision.status === 'validated' && Number.isInteger(decision.selectedSolution)
    ? Math.max(0, Math.min(decision.selectedSolution, state.result.solutions.length - 1))
    : 0;
  state.explicitSolutionSelection = decision.status === 'validated';
  state.selectedVehicle = 0;
  state.selectedPlacementId = null;
  renderResults();
  switchTab('results');
}
$('#refresh-history').addEventListener('click', () => loadHistory(true));
['#history-filter-status', '#history-filter-user', '#history-filter-type', '#history-filter-case', '#history-filter-from', '#history-filter-to'].forEach(selector => {
  $(selector).addEventListener(selector.includes('user') || selector.includes('type') || selector.includes('case') ? 'input' : 'change', () => renderHistoryList());
});
async function duplicateRun(id) {
  const run = await fetchRunDetail(id);
  const request = run.request;
  state.currentRequest = request;
  syncItemMeta();
  $('#cargo-table tbody').innerHTML = '';
  (request.items || []).forEach(addRow);
  if (request.vehicle_policy?.forced_vehicle_id) $('#vehicle-id').value = request.vehicle_policy.forced_vehicle_id;
  if (request.budget_seconds) $('#budget-seconds').value = String(request.budget_seconds);
  if (request.seed != null) $('#seed').value = request.seed;
  if (request.vehicle_policy?.max_vehicles) $('#max-vehicles').value = request.vehicle_policy.max_vehicles;
  if (request.default_margins?.left != null) $('#default-margin').value = request.default_margins.left;
  updateSelectedVehicleSummary();
  switchTab('data');
}

function filterConnectionsByDays(days) {
  const threshold = new Date();
  threshold.setHours(0, 0, 0, 0);
  threshold.setDate(threshold.getDate() - (days - 1));
  return connectionStore.filter(entry => new Date(entry.timestamp) >= threshold);
}
function renderMetricCards(metrics) {
  $('#dashboard-cards').innerHTML = [
    ['Connexions totales', metrics.connections.total, metrics.connections.last ? `Dernière connexion : ${formatDateTime(metrics.connections.last)}` : 'Aucune connexion'],
    ['Connexions aujourd’hui', metrics.connections.today, `${metrics.connections.last7} sur 7 jours · ${metrics.connections.last30} sur 30 jours`],
    ['Optimisations réalisées', metrics.total, 'Total des cas présents dans l’historique'],
    ['Cas validés', metrics.validated, `${fmt(metrics.validationRate, 1)} % de validation`],
    ['Cas en échec', metrics.failed, `${fmt(metrics.failureRate, 1)} % d’échec`],
    ['Cas non enregistrés', metrics.pending, 'Aucune décision finale encore saisie'],
  ].map(([label, value, helper]) => `
    <article class="metric-card">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${helper}</small>
    </article>`).join('');
}
function renderStatusDonut(metrics) {
  const total = Math.max(1, metrics.total);
  const validatedPct = metrics.validated / total * 100;
  const failedPct = metrics.failed / total * 100;
  const pendingPct = metrics.pending / total * 100;
  const donut = $('#status-donut');
  donut.style.background = `conic-gradient(var(--success) 0 ${validatedPct}%, var(--danger) ${validatedPct}% ${validatedPct + failedPct}%, var(--warning) ${validatedPct + failedPct}% 100%)`;
  donut.innerHTML = `<span><strong>${metrics.total}</strong><small>cas</small></span>`;
  $('#status-legend').innerHTML = [
    ['Validés', metrics.validated, validatedPct, 'status-validated'],
    ['Échecs', metrics.failed, failedPct, 'status-failed'],
    ['Non enregistrés', metrics.pending, pendingPct, 'status-pending'],
  ].map(([label, count, pct, cls]) => `<div class="status-legend-item"><span class="legend-dot ${cls}"></span><div><strong>${label}</strong><small>${count} cas · ${fmt(pct, 1)} %</small></div></div>`).join('');
}
function dashboardRange() {
  const period = $('#dashboard-period').value;
  if (period === 'today') {
    const day = isoNow().slice(0, 10);
    return { from: day, to: day, label: 'Aujourd’hui' };
  }
  if (period === '7days' || period === '30days') {
    const days = period === '7days' ? 7 : 30;
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - (days - 1));
    return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10), label: `${days} jours` };
  }
  return { from: $('#dashboard-from').value, to: $('#dashboard-to').value, label: 'Période personnalisée' };
}
function buildBuckets(range) {
  const buckets = [];
  if (!range.from || !range.to) return buckets;
  const cursor = new Date(range.from);
  const end = new Date(range.to);
  while (cursor <= end) {
    buckets.push({ key: cursor.toISOString().slice(0, 10), label: cursor.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }), optimizations: 0, validated: 0, failed: 0, connections: 0 });
    cursor.setDate(cursor.getDate() + 1);
  }
  return buckets;
}
function renderActivityChart(runs) {
  const range = dashboardRange();
  const buckets = buildBuckets(range);
  const index = Object.fromEntries(buckets.map(bucket => [bucket.key, bucket]));
  runs.forEach(run => {
    const key = String(run.created_at || '').slice(0, 10);
    if (!index[key]) return;
    index[key].optimizations += 1;
    const status = effectiveRunStatus(run);
    if (status === 'validated') index[key].validated += 1;
    if (status === 'failed') index[key].failed += 1;
  });
  connectionStore.forEach(entry => {
    const key = String(entry.timestamp || '').slice(0, 10);
    if (index[key]) index[key].connections += 1;
  });
  const max = Math.max(1, ...buckets.flatMap(bucket => [bucket.optimizations, bucket.validated, bucket.failed, bucket.connections]));
  $('#activity-chart').innerHTML = buckets.length ? `
    <div class="activity-bars">
      ${buckets.map(bucket => `
        <div class="activity-group">
          <div class="activity-column-set">
            <span class="activity-bar optimizations" style="height:${bucket.optimizations / max * 140}px" title="Optimisations : ${bucket.optimizations}"></span>
            <span class="activity-bar validated" style="height:${bucket.validated / max * 140}px" title="Validés : ${bucket.validated}"></span>
            <span class="activity-bar failed" style="height:${bucket.failed / max * 140}px" title="Échecs : ${bucket.failed}"></span>
            <span class="activity-bar connections" style="height:${bucket.connections / max * 140}px" title="Connexions : ${bucket.connections}"></span>
          </div>
          <small>${bucket.label}</small>
        </div>`).join('')}
    </div>
    <div class="chart-legend-inline">
      <span><i class="legend-chip optimizations"></i>Optimisations</span>
      <span><i class="legend-chip validated"></i>Validés</span>
      <span><i class="legend-chip failed"></i>Échecs</span>
      <span><i class="legend-chip connections"></i>Connexions</span>
    </div>` : '<div class="empty-state">Choisissez une période valide pour afficher l’évolution.</div>';
}
async function renderDashboard() {
  try {
    const runs = await getHistoryRuns();
    const metrics = {
      total: runs.length,
      validated: runs.filter(run => effectiveRunStatus(run) === 'validated').length,
      failed: runs.filter(run => effectiveRunStatus(run) === 'failed').length,
      pending: runs.filter(run => effectiveRunStatus(run) === 'pending').length,
      connections: {
        total: connectionStore.length,
        today: filterConnectionsByDays(1).length,
        last7: filterConnectionsByDays(7).length,
        last30: filterConnectionsByDays(30).length,
        last: connectionStore.length ? connectionStore[connectionStore.length - 1].timestamp : '',
      },
    };
    const closedCases = metrics.validated + metrics.failed;
    metrics.validationRate = closedCases ? metrics.validated / closedCases * 100 : 0;
    metrics.failureRate = closedCases ? metrics.failed / closedCases * 100 : 0;
    renderMetricCards(metrics);
    renderStatusDonut(metrics);
    renderActivityChart(runs);
    document.querySelectorAll('.dashboard-custom-range').forEach(el => el.classList.toggle('hidden', $('#dashboard-period').value !== 'custom'));
  } catch (error) {
    $('#dashboard-cards').innerHTML = `<div class="empty-state">${escapeHtml(error.message || String(error))}</div>`;
  }
}
$('#dashboard-period').addEventListener('change', () => renderDashboard());
$('#dashboard-from').addEventListener('change', () => renderDashboard());
$('#dashboard-to').addEventListener('change', () => renderDashboard());

loadHistory();
renderDashboard();
