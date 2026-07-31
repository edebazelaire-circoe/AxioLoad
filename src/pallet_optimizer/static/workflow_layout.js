(() => {
  'use strict';
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];
  const FLEET_KEY = 'axioload.fleet.v1';

  function vehicles(){ return window.PLO_VEHICLES || []; }
  function loadFleet(){
    try {
      const saved = JSON.parse(localStorage.getItem(FLEET_KEY) || '[]');
      if (Array.isArray(saved) && saved.length) return saved;
    } catch (_) {}
    const first = vehicles()[0];
    return first ? [{vehicle_id:first.model_id, quantity:1}] : [];
  }
  let fleet = loadFleet();
  function saveFleet(){ try { localStorage.setItem(FLEET_KEY, JSON.stringify(fleet)); } catch (_) {} }
  function syncLegacyFields(){
    const valid = fleet.filter(x => x.vehicle_id && Number(x.quantity) > 0);
    const selected = valid[0];
    if ($('#vehicle-id') && selected) {
      $('#vehicle-id').value = selected.vehicle_id;
      $('#vehicle-id').dispatchEvent(new Event('change', {bubbles:true}));
    }
    const total = valid.reduce((sum, x) => sum + Math.max(0, Number(x.quantity)||0), 0);
    if ($('#max-vehicles')) $('#max-vehicles').value = Math.max(1, total);
    const totalAvailable = $('#total-available-vehicles');
    if (totalAvailable) totalAvailable.value = Math.max(1, total);
  }

  function renderFleet(){
    const list = $('#fleet-lines'); if (!list) return;
    list.innerHTML = '';
    fleet.forEach((entry, index) => {
      const row = document.createElement('div'); row.className='fleet-line';
      row.innerHTML = `<select aria-label="Type de camion">${vehicles().map(v=>`<option value="${v.model_id}" ${v.model_id===entry.vehicle_id?'selected':''}>${v.name}</option>`).join('')}</select><label>Nombre<input type="number" min="1" value="${Math.max(1,Number(entry.quantity)||1)}"></label><button type="button" class="row-delete" aria-label="Supprimer ce type">×</button>`;
      const select=$('select',row), qty=$('input',row);
      select.addEventListener('change',()=>{entry.vehicle_id=select.value;saveFleet();syncLegacyFields();});
      qty.addEventListener('change',()=>{entry.quantity=Math.max(1,Number(qty.value)||1);qty.value=entry.quantity;saveFleet();syncLegacyFields();});
      $('.row-delete',row).addEventListener('click',()=>{if(fleet.length===1)return;fleet.splice(index,1);saveFleet();renderFleet();syncLegacyFields();});
      list.append(row);
    });
    syncLegacyFields();
  }

  function installFleet(){
    const grid = $('#tab-data .settings-grid'); if(!grid || $('#fleet-card')) return;
    const card=document.createElement('section'); card.id='fleet-card'; card.className='fleet-card';
    card.innerHTML=`<div class="fleet-heading"><div><h3>Flotte disponible</h3><p>Déclarez les types de camions réellement disponibles et leur quantité.</p></div><button id="add-fleet-line" type="button" class="secondary">+ Ajouter un camion</button></div><div id="fleet-lines"></div>`;
    grid.before(card);
    $('#add-fleet-line').addEventListener('click',()=>{const used=new Set(fleet.map(x=>x.vehicle_id));const next=vehicles().find(v=>!used.has(v.model_id))||vehicles()[0];if(!next)return;fleet.push({vehicle_id:next.model_id,quantity:1});saveFleet();renderFleet();});
    renderFleet();
    const vehicleLabel=$('#vehicle-id')?.closest('label'); if(vehicleLabel) vehicleLabel.classList.add('legacy-fleet-field');
    const maxLabel=$('#max-vehicles')?.closest('label'); if(maxLabel) maxLabel.classList.add('legacy-fleet-field');
    $('#selected-vehicle-summary')?.classList.add('compact-hidden');
  }

  function moveCalculationControls(){
    const budget=$('#budget-seconds')?.closest('label');
    const optimize=$('#optimize');
    if(budget && optimize && !$('#calculation-toolbar')){
      const bar=document.createElement('div');bar.id='calculation-toolbar';bar.className='calculation-toolbar';
      optimize.parentElement?.insertBefore(bar,optimize);bar.append(budget);bar.append(optimize);
    }
    const routeBudget=$('#route-time-limit')?.closest('label') || $('#route-budget-seconds')?.closest('label');
    const actions=$('.route-method-actions'); if(routeBudget&&actions) actions.prepend(routeBudget);
    const seed=$('#route-seed')?.closest('label') || $('#route-seed')?.parentElement; if(seed) seed.remove();
  }

  function polishImport(){
    const box=$('#tab-data .import-box'); if(!box) return; box.classList.add('polished-import');
    const help=$('#import-format-help'); if(help) box.append(help);
  }
  function renameDestination(){
    $$('#cargo-table thead th').forEach(th=>{if(th.childNodes[0]?.textContent?.trim().toLowerCase()==='destination') th.childNodes[0].textContent='Client ';});
  }
  function polishVehicles(){
    const table=$('#vehicle-table'); if(!table)return;
    table.classList.add('vehicle-table-simplified');
    $$('#vehicle-table tbody tr').forEach(row=>{
      const model=row.querySelector('[data-v="model_id"]');
      const name=row.querySelector('[data-v="name"]');
      if(model?.readOnly){row.classList.add('global-vehicle-row');$$('input',row).forEach(i=>i.disabled=true);}
      row.querySelector('.vehicle-origin-badge')?.remove();
    });
  }
  function polishTotalBox(){
    const count=$('#total-available-vehicles')?.closest('label'); if(count) count.classList.add('legacy-fleet-field');
  }
  function publishFleet(){
    window.AxioFleet={get:()=>fleet.map(x=>({...x,quantity:Number(x.quantity)||1}))};
    const native=window.fetch.bind(window);
    window.fetch=async(input,init={})=>{
      const url=typeof input==='string'?input:input?.url||'';
      if(url.includes('/api/total/optimize')&&typeof init.body==='string'){
        try{const body=JSON.parse(init.body);body.vehicle_fleet=window.AxioFleet.get();init={...init,body:JSON.stringify(body)};}catch(_){}
      }
      return native(input,init);
    };
  }
  function init(){installFleet();moveCalculationControls();polishImport();renameDestination();polishVehicles();polishTotalBox();publishFleet();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
