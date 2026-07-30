(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const checkbox = $('#total-optimization-enabled');
  const inputsPanel = $('#total-route-inputs');
  const cargoBody = $('#cargo-table tbody');
  const message = $('#data-errors');
  const mapCanvas = $('#total-map');
  const mapCtx = mapCanvas?.getContext('2d');
  const state = {
    depot: null,
    result: null,
    selected: 0,
    colors: new Map(),
    zoom: 6,
    center: { lat: 46.7, lon: 2.5 },
    panX: 0,
    panY: 0,
    drag: null,
    tiles: new Map(),
  };

  const colors = ['#007A9C','#E26D3D','#7A5CC7','#0C9A83','#D04E8C','#9A6B12','#3C7DC4','#A84A42','#4E8B3A','#B95B9A','#6E7280','#C3781D'];
  const TILE = 256;

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }
  function fmt(value, digits=1) {
    return Number(value || 0).toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  function show(messageText, error=false) {
    if (!message) return;
    message.textContent = messageText;
    message.classList.toggle('hidden', !messageText);
    message.classList.toggle('error', Boolean(error));
    message.classList.toggle('success', Boolean(messageText) && !error);
  }
  function clientColor(client) {
    const key=String(client || 'Client').trim().toLowerCase();
    if (!state.colors.has(key)) state.colors.set(key, colors[state.colors.size % colors.length]);
    return state.colors.get(key);
  }
  function vehicleIcon(modelId='', name='') {
    const value=`${modelId} ${name}`.toLowerCase();
    if (value.includes('container_20') || value.includes('20 pieds') || value.includes("20'")) return '📦';
    if (value.includes('container_40') || value.includes('40 pieds') || value.includes("40'")) return '📦';
    if (value.includes('semi')) return '🚛';
    if (value.includes('rigid') || value.includes('porteur')) return '🚚';
    return '🚐';
  }
  function decorateVehicleLabels() {
    const select=$('#vehicle-id');
    select?.querySelectorAll('option').forEach(option=>{
      if (option.dataset.vehicleIcon === '1') return;
      const vehicle=(window.PLO_VEHICLES || []).find(entry=>entry.model_id===option.value);
      option.textContent=`${vehicleIcon(option.value,vehicle?.name || option.textContent)} ${option.textContent}`;
      option.dataset.vehicleIcon='1';
    });
    const summary=$('#selected-vehicle-summary strong');
    if (summary && summary.dataset.vehicleIcon !== '1') {
      const selected=(window.PLO_VEHICLES || []).find(entry=>entry.model_id===select?.value);
      summary.textContent=`${vehicleIcon(select?.value,selected?.name || summary.textContent)} ${summary.textContent}`;
      summary.dataset.vehicleIcon='1';
    }
  }
  function configureInterface() {
    const nav=$('.tabs');
    const labels={vehicles:'Véhicules',data:'Données',results:'Chargement',route:'Itinéraire',total:'Optimisation totale',history:'Historique'};
    ['vehicles','data','results','route','total','history'].forEach((name,index)=>{
      const button=$(`.tab[data-tab="${name}"]`);
      if (!button) return;
      button.textContent=`${index}. ${labels[name]}`;
      nav?.append(button);
    });

    const budgetLabel=$('#budget-seconds')?.closest('label')?.querySelector('.field-label');
    if (budgetLabel) budgetLabel.textContent='Temps de calcul';
    const routeBudgetLabel=$('#route-time-limit')?.closest('label')?.querySelector('span');
    if (routeBudgetLabel) routeBudgetLabel.textContent='Temps de calcul';

    const seedLabel=$('#seed')?.closest('label');
    if (seedLabel) seedLabel.hidden=true;

    const marginLabel=$('#default-margin')?.closest('label')?.querySelector('.field-label');
    if (marginLabel && !marginLabel.querySelector('.help-tip')) {
      marginLabel.append(' ');
      const help=document.createElement('button');
      help.type='button';
      help.className='help-tip small-tip';
      help.dataset.tooltip='Espace libre ajouté autour de chaque marchandise pour tenir compte des jeux de manutention, protections et tolérances. Cette valeur réduit les dimensions réellement utilisables.';
      help.setAttribute('aria-label','Définition de la marge de sécurité');
      help.textContent='?';
      marginLabel.append(help);
      if (typeof bindHelpTips === 'function') bindHelpTips(marginLabel);
    }

    const settings=$('.total-route-settings');
    if (settings && !$('#total-available-vehicles')) {
      const field=document.createElement('label');
      field.className='total-fleet-field';
      field.innerHTML='<span>Nombre de camions disponibles <button type="button" class="help-tip small-tip" data-tooltip="Nombre maximal de camions que l’optimisation totale peut utiliser pour construire les tournées et leurs plans de chargement." aria-label="Définition du nombre de camions disponibles">?</button></span><input id="total-available-vehicles" type="number" min="1" max="50" value="5">';
      const current=Number($('#max-vehicles')?.value || 5);
      field.querySelector('input').value=String(Math.max(1,current));
      settings.insertBefore(field, settings.children[1] || null);
      if (typeof bindHelpTips === 'function') bindHelpTips(field);
    }

    const description=checkbox?.closest('.total-mode-toggle')?.querySelector('small');
    if (description) description.textContent='Couple le nombre de camions disponibles, le rangement LIFO et les distances de tournée. Les produits d’un même client restent toujours dans le même camion.';
    decorateVehicleLabels();
  }
  configureInterface();

  function parseCoordinates(value) {
    const match=String(value || '').trim().match(/^\s*(-?\d{1,2}(?:[.,]\d+)?)\s*[,;]\s*(-?\d{1,3}(?:[.,]\d+)?)\s*$/);
    if (!match) return null;
    const lat=Number(match[1].replace(',','.')), lon=Number(match[2].replace(',','.'));
    if (!Number.isFinite(lat)||!Number.isFinite(lon)||lat < -90||lat > 90||lon < -180||lon > 180) return null;
    return { lat, lon, display_name:`${lat.toFixed(6)}, ${lon.toFixed(6)}` };
  }
  async function geocode(address) {
    const manual=parseCoordinates(address);
    if (manual) return manual;
    const response=await fetch(`/api/route/geocode?q=${encodeURIComponent(address)}`);
    const body=await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(body.detail || 'Adresse introuvable.');
    if (!body.results?.length) throw new Error(`Aucun résultat trouvé pour « ${address} ».`);
    return body.results[0];
  }
  function prefix(type) { return `total${type[0].toUpperCase()}${type.slice(1)}`; }
  function rowReady(row) {
    return ['Pickup','Delivery'].every(type => Number.isFinite(Number(row.dataset[`total${type}Lat`])) && Number.isFinite(Number(row.dataset[`total${type}Lon`] )));
  }
  function updateRowStatus(row) {
    const status=row.querySelector('.total-row-status');
    if (!status) return;
    const pickup=Number.isFinite(Number(row.dataset.totalPickupLat));
    const delivery=Number.isFinite(Number(row.dataset.totalDeliveryLat));
    status.className='total-row-status';
    if (pickup && delivery) { status.classList.add('ready'); status.textContent='Prête'; }
    else if (pickup || delivery) { status.classList.add('partial'); status.textContent='Partielle'; }
    else status.textContent='À localiser';
  }
  function invalidate(row,type) {
    const p=prefix(type);
    delete row.dataset[`${p}Lat`]; delete row.dataset[`${p}Lon`]; delete row.dataset[`${p}Label`];
    updateRowStatus(row);
  }
  function bindRow(row) {
    if (row.dataset.totalBound !== '1') {
      row.dataset.totalBound='1';
      ['pickup','delivery'].forEach(type => {
        const input=row.querySelector(`[data-total="${type}_address"]`);
        const button=row.querySelector(`[data-total-location="${type}"]`);
        input?.addEventListener('input',()=>invalidate(row,type));
        button?.addEventListener('click',()=>locateRow(row,type,button));
      });
    }
    updateRowStatus(row);
  }
  function toggleOrderColumn(active) {
    const heading=$('#cargo-table thead .col-order');
    if (heading) heading.hidden=active;
    $$('#cargo-table tbody [data-k="delivery_order"]').forEach(input=>{
      const cell=input.closest('td');
      if (cell) cell.hidden=active;
      input.disabled=active;
    });
    const hint=$$('.hint').find(element=>element.textContent.includes('Ordre de livraison'));
    if (hint) hint.hidden=active;
  }
  function bindRows() {
    $$('#cargo-table tbody tr').forEach(bindRow);
    toggleOrderColumn(Boolean(checkbox?.checked));
    decorateVehicleLabels();
  }
  const observer=new MutationObserver(bindRows);
  if (cargoBody) observer.observe(cargoBody,{childList:true,subtree:true});
  const vehicleObserver=new MutationObserver(decorateVehicleLabels);
  if ($('#vehicle-id')) vehicleObserver.observe($('#vehicle-id'),{childList:true});
  if ($('#selected-vehicle-summary')) vehicleObserver.observe($('#selected-vehicle-summary'),{childList:true,subtree:true});
  bindRows();

  async function locateRow(row,type,button) {
    const input=row.querySelector(`[data-total="${type}_address"]`);
    const address=input?.value.trim();
    if (!address) { show(`Renseignez le point ${type === 'pickup' ? 'd’enlèvement' : 'de livraison'}.`,true); return false; }
    const original=button.textContent; button.disabled=true; button.textContent='…';
    try {
      const result=await geocode(address); const p=prefix(type);
      row.dataset[`${p}Lat`]=result.lat; row.dataset[`${p}Lon`]=result.lon; row.dataset[`${p}Label`]=result.display_name;
      input.value=result.display_name; updateRowStatus(row); show('Adresse localisée.'); return true;
    } catch(error) { show(error.message || String(error),true); return false; }
    finally { button.disabled=false; button.textContent=original; }
  }
  async function locateDepot() {
    const address=$('#total-depot-address').value.trim();
    if (!address) { show('Renseignez le lieu actuel du camion.',true); return false; }
    const button=$('#total-geocode-depot'), status=$('#total-depot-status');
    const original=button.textContent; button.disabled=true; button.textContent='Localisation…';
    try {
      const result=await geocode(address);
      state.depot={lat:Number(result.lat),lon:Number(result.lon),label:result.display_name};
      $('#total-depot-address').value=result.display_name;
      status.textContent=`Localisé : ${Number(result.lat).toFixed(5)}, ${Number(result.lon).toFixed(5)}`;
      status.className='total-location-status ready'; show('Lieu actuel localisé.'); return true;
    } catch(error) { status.textContent='Localisation impossible.'; status.className='total-location-status error'; show(error.message || String(error),true); return false; }
    finally { button.disabled=false; button.textContent=original; }
  }
  $('#total-geocode-depot')?.addEventListener('click',locateDepot);
  $('#total-depot-address')?.addEventListener('input',()=>{state.depot=null; const status=$('#total-depot-status'); status.textContent='Adresse non localisée.'; status.className='total-location-status';});
  $('#total-fill-pickups')?.addEventListener('click',async()=>{
    if (!state.depot && !(await locateDepot())) return;
    $$('#cargo-table tbody tr').forEach(row=>{
      const input=row.querySelector('[data-total="pickup_address"]');
      if (!input.value.trim()) input.value=state.depot.label;
      row.dataset.totalPickupLat=state.depot.lat; row.dataset.totalPickupLon=state.depot.lon; row.dataset.totalPickupLabel=state.depot.label; updateRowStatus(row);
    });
    show('Le lieu actuel du camion est utilisé comme point d’enlèvement pour les lignes vides.');
  });
  $('#total-geocode-all')?.addEventListener('click',async()=>{
    if (!state.depot && !(await locateDepot())) return;
    const rows=$$('#cargo-table tbody tr');
    for (const row of rows) {
      for (const type of ['pickup','delivery']) {
        const p=prefix(type);
        if (Number.isFinite(Number(row.dataset[`${p}Lat`]))) continue;
        const button=row.querySelector(`[data-total-location="${type}"]`);
        if (!(await locateRow(row,type,button))) return;
        await new Promise(resolve=>setTimeout(resolve,250));
      }
    }
    show('Toutes les adresses sont localisées.');
  });

  function applyMode() {
    const active=Boolean(checkbox?.checked);
    document.body.classList.toggle('total-mode-enabled',active);
    inputsPanel?.classList.toggle('hidden',!active);
    const button=$('#optimize');
    if (button && !button.disabled) button.textContent=active ? 'Lancer l’optimisation totale' : 'Optimiser le chargement';
    toggleOrderColumn(active);
    bindRows();
  }
  checkbox?.addEventListener('change',applyMode);
  applyMode();

  function shapeUnit(shape,quantity) {
    if (shape === 'pallet') return quantity > 1 ? 'palettes':'palette';
    if (shape === 'box') return quantity > 1 ? 'colis':'colis';
    return quantity > 1 ? 'unités':'unité';
  }
  function rowValue(row,key) {
    const input=row.querySelector(`[data-k="${key}"]`);
    return input?.type === 'number' ? Number(input.value) : input?.value?.trim();
  }
  function samePoint(left,right) {
    return Math.abs(left.lat-right.lat) < 1e-7 && Math.abs(left.lon-right.lon) < 1e-7;
  }
  function buildTotalPayload(loadingPayload) {
    if (!state.depot) throw new Error('Localisez le lieu actuel du camion.');
    const availableVehicles=Number($('#total-available-vehicles')?.value || 0);
    if (!Number.isInteger(availableVehicles) || availableVehicles < 1) throw new Error('Indiquez un nombre de camions disponibles supérieur ou égal à 1.');

    const groupedJobs=new Map();
    $$('#cargo-table tbody tr').forEach((row,index)=>{
      if (!rowReady(row)) throw new Error(`Localisez l’enlèvement et la livraison de la ligne ${index+1}.`);
      const id=rowValue(row,'id'), quantity=Number(rowValue(row,'quantity') || 1), shape=rowValue(row,'shape'), client=rowValue(row,'destination') || id;
      const pickup={lat:Number(row.dataset.totalPickupLat),lon:Number(row.dataset.totalPickupLon),label:row.dataset.totalPickupLabel || row.querySelector('[data-total="pickup_address"]').value};
      const delivery={lat:Number(row.dataset.totalDeliveryLat),lon:Number(row.dataset.totalDeliveryLon),label:row.dataset.totalDeliveryLabel || row.querySelector('[data-total="delivery_address"]').value};
      const key=String(client).trim().toLocaleLowerCase('fr-FR');
      const unitType=shapeUnit(shape,quantity);
      const existing=groupedJobs.get(key);
      if (existing) {
        if (!samePoint(existing.pickup,pickup) || !samePoint(existing.delivery,delivery)) {
          throw new Error(`Toutes les marchandises du client « ${client} » doivent utiliser les mêmes points d’enlèvement et de livraison afin de rester dans un seul camion.`);
        }
        existing.item_ids.push(id);
        existing.reference=existing.item_ids.join(', ');
        existing.quantity+=quantity;
        existing.weight_kg+=Number(rowValue(row,'weight') || 0) * quantity;
        if (existing.unit_type !== unitType) existing.unit_type='unités mixtes';
        return;
      }
      groupedJobs.set(key,{
        id:`JOB-${groupedJobs.size+1}-${id}`,
        client,
        reference:id,
        item_ids:[id],
        quantity,
        unit_type:unitType,
        weight_kg:Number(rowValue(row,'weight') || 0) * quantity,
        pickup,
        delivery,
      });
    });

    const loading=JSON.parse(JSON.stringify(loadingPayload));
    loading.vehicle_policy={...(loading.vehicle_policy || {}),max_vehicles:availableVehicles};
    return {
      loading,
      route:{depot:state.depot,jobs:[...groupedJobs.values()],return_to_depot:$('#total-return-depot').checked,_fetch_geometry:true},
      time_limit_s:Number(loading.budget_seconds || 30),
      seed:Number(loading.seed || 1),
    };
  }

  async function run(loadingPayload) {
    show('');
    const payload=buildTotalPayload(loadingPayload);
    const response=await fetch('/api/total/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const body=await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(body.detail || 'L’optimisation totale a échoué.');
    state.result=body; state.selected=0; resetMap(); render();
    if (typeof switchTab === 'function') switchTab('total');
    else document.querySelector('[data-tab="total"]')?.click();
  }

  function methodCard(solution,index) {
    const card=document.createElement('button'); card.type='button';
    card.className=`total-method-card ${index===state.selected?'active':''} ${solution.rank===1?'best':''}`;
    card.innerHTML=`<div class="total-method-title"><strong>${esc(solution.method_name)} <span class="help-tip small-tip total-method-help" title="${esc(solution.method_description)}" aria-label="Définition de la méthode">?</span></strong><span>${solution.rank===1?'MEILLEUR COMPROMIS':''}</span></div>
      <div class="total-method-metrics">
        <span><small>Véhicules</small><strong>${solution.vehicle_count}</strong></span>
        <span><small>Distance</small><strong>${fmt(solution.total_distance_km)} km</strong></span>
        <span><small>Mètres linéaires</small><strong>${fmt(solution.total_linear_meters,2)} m.l.</strong></span>
        <span><small>Calcul</small><strong>${fmt(solution.elapsed_seconds,2)} s</strong></span>
      </div>
      <small>${Number(solution.iterations||0).toLocaleString('fr-FR')} itérations · ${solution.oracle_calls} contrôles 3D · ${solution.oracle_cache_hits} résultats réutilisés</small>`;
    card.addEventListener('click',()=>{state.selected=index;resetMap();render();}); return card;
  }
  function render() {
    if (!state.result?.solutions?.length) return;
    $('#total-empty').classList.add('hidden'); $('#total-results').classList.remove('hidden');
    $('#total-run-meta').textContent=`${fmt(state.result.elapsed_seconds,2)} s · ${state.result.solutions.length} méthodes comparées`;
    const cards=$('#total-method-cards'); cards.innerHTML=''; state.result.solutions.forEach((s,i)=>cards.append(methodCard(s,i)));
    const solution=state.result.solutions[state.selected];
    $('#total-summary-title').textContent=`${solution.method_name} · ${solution.vehicle_count} véhicule(s)`;
    $('#total-summary-subtitle').textContent=solution.objective_priority;
    $('#total-summary-metrics').innerHTML=`<span><small>Distance totale</small><strong>${fmt(solution.total_distance_km)} km</strong></span><span><small>Durée</small><strong>${fmt(solution.total_duration_min/60)} h</strong></span><span><small>Poids</small><strong>${fmt(solution.total_weight_kg,0)} kg</strong></span><span><small>Unités</small><strong>${solution.total_handling_units}</strong></span>`;
    $('#total-model-description').textContent=solution.method_description;
    $('#total-model-note').textContent=`${state.result.model_note} ${state.result.objective_note}`;
    $('#total-map-subtitle').textContent=`${solution.vehicle_count} tournée(s) · ${fmt(solution.total_distance_km)} km`;
    renderLegend(solution); renderRoutes(solution); fitMap(solution); drawMap();
  }
  function renderLegend(solution) {
    $('#total-map-legend').innerHTML=solution.routes.map((route,index)=>`<span><i style="--route-color:${colors[index%colors.length]}"></i>Véhicule ${index+1} · ${fmt(route.distance_km)} km</span>`).join('');
  }
  function renderRoutes(solution) {
    const list=$('#total-route-list');
    list.innerHTML=solution.routes.map((route,index)=>{
      const color=colors[index%colors.length];
      const clients=route.clients.map(client=>`<tr><td><span class="total-client-dot" style="--client-color:${clientColor(client.client)}"></span><strong>${esc(client.client)}</strong></td><td>${esc(client.pickup_label)}</td><td>${esc(client.delivery_label)}</td><td>${client.quantity} ${esc(client.unit_type)}</td><td>${fmt(client.weight_kg,0)} kg</td></tr>`).join('');
      const placements=route.loading_plan?.placements || [];
      return `<article class="total-route-card" style="--route-color:${color}">
        <div class="total-route-heading"><div><strong>Véhicule ${index+1} · ${esc(route.vehicle_name)}</strong><small>${fmt(route.distance_km)} km · ${fmt(route.duration_min)} min · ${fmt(route.weight_kg,0)} kg</small></div><div><strong>${fmt(route.linear_meters,2)} m.l.</strong><small>${esc(route.loading_method_name)}</small></div></div>
        <div class="total-orders"><span><strong>Enlèvements :</strong> ${route.pickup_order.map(esc).join(' → ')}</span><span><strong>Livraisons :</strong> ${route.delivery_order.map(esc).join(' → ')}</span></div>
        <div class="table-wrap"><table class="total-client-table"><thead><tr><th>Client</th><th>Enlèvement</th><th>Livraison</th><th>Quantité</th><th>Poids</th></tr></thead><tbody>${clients}</tbody></table></div>
        <details><summary>Voir le plan de chargement (${placements.length} objet(s))</summary><div class="table-wrap"><table><thead><tr><th>Objet</th><th>X</th><th>Y longitudinal</th><th>Orientation</th><th>L × l × H</th></tr></thead><tbody>${placements.map(p=>`<tr><td>${esc(p.item_id)}</td><td>${p.x_mm} mm</td><td>${p.y_mm} mm</td><td>${p.orientation_deg}°</td><td>${p.actual_length_mm} × ${p.actual_width_mm} × ${p.actual_height_mm} mm</td></tr>`).join('')}</tbody></table></div></details>
      </article>`;
    }).join('');
  }

  function clampLat(lat){return Math.max(-85.0511,Math.min(85.0511,lat));}
  function world(lat,lon,z){const sin=Math.sin(clampLat(lat)*Math.PI/180),scale=TILE*(2**z);return{x:(lon+180)/360*scale,y:(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*scale};}
  function screen(lat,lon){const w=world(lat,lon,state.zoom),c=world(state.center.lat,state.center.lon,state.zoom);return{x:mapCanvas.width/2+state.panX+w.x-c.x,y:mapCanvas.height/2+state.panY+w.y-c.y};}
  function fitMap(solution){
    const points=solution.routes.flatMap(route=>(route.geometry?.length?route.geometry:route.stops.map(s=>[s.lat,s.lon]))).filter(p=>Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1])));
    if(!points.length)return;
    const lats=points.map(p=>Number(p[0])),lons=points.map(p=>Number(p[1])); state.center={lat:(Math.min(...lats)+Math.max(...lats))/2,lon:(Math.min(...lons)+Math.max(...lons))/2}; state.panX=state.panY=0;
    for(let z=15;z>=2;z--){const coords=points.map(p=>world(Number(p[0]),Number(p[1]),z)),spanX=Math.max(...coords.map(c=>c.x))-Math.min(...coords.map(c=>c.x)),spanY=Math.max(...coords.map(c=>c.y))-Math.min(...coords.map(c=>c.y));if(spanX<mapCanvas.width-150&&spanY<mapCanvas.height-150){state.zoom=z;break;}}
  }
  function resetMap(){state.zoom=6;state.center={lat:46.7,lon:2.5};state.panX=state.panY=0;}
  function tileUrl(z,x,y){return `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;}
  function drawTiles(){
    if(!mapCtx)return; const c=world(state.center.lat,state.center.lon,state.zoom),left=c.x-mapCanvas.width/2-state.panX,top=c.y-mapCanvas.height/2-state.panY;
    const x0=Math.floor(left/TILE),y0=Math.floor(top/TILE),x1=Math.ceil((left+mapCanvas.width)/TILE),y1=Math.ceil((top+mapCanvas.height)/TILE),max=2**state.zoom;
    for(let tx=x0;tx<=x1;tx++)for(let ty=y0;ty<=y1;ty++){if(ty<0||ty>=max)continue;const wrapped=((tx%max)+max)%max,key=`${state.zoom}/${wrapped}/${ty}`,dx=tx*TILE-left,dy=ty*TILE-top;let img=state.tiles.get(key);if(!img){img=new Image();img.crossOrigin='anonymous';img.onload=drawMap;img.src=tileUrl(state.zoom,wrapped,ty);state.tiles.set(key,img);}if(img.complete&&img.naturalWidth)mapCtx.drawImage(img,dx,dy,TILE,TILE);}
  }
  function drawMap(){
    if(!mapCtx||!state.result)return; const solution=state.result.solutions[state.selected]; mapCtx.clearRect(0,0,mapCanvas.width,mapCanvas.height);mapCtx.fillStyle=document.documentElement.dataset.theme==='dark'?'#102D39':'#E7F1F4';mapCtx.fillRect(0,0,mapCanvas.width,mapCanvas.height);drawTiles();
    solution.routes.forEach((route,index)=>{const color=colors[index%colors.length],geometry=route.geometry?.length?route.geometry:route.stops.map(s=>[s.lat,s.lon]);mapCtx.save();mapCtx.strokeStyle='rgba(255,255,255,.75)';mapCtx.lineWidth=7;mapCtx.beginPath();geometry.forEach((p,i)=>{const q=screen(Number(p[0]),Number(p[1]));i?mapCtx.lineTo(q.x,q.y):mapCtx.moveTo(q.x,q.y);});mapCtx.stroke();mapCtx.strokeStyle=color;mapCtx.lineWidth=4;mapCtx.stroke();mapCtx.restore();route.stops.forEach(stop=>{const q=screen(stop.lat,stop.lon),fill=(stop.type==='pickup'||stop.type==='delivery')?clientColor(stop.client):'#063B5B';mapCtx.beginPath();mapCtx.arc(q.x,q.y,8,0,Math.PI*2);mapCtx.fillStyle=fill;mapCtx.fill();mapCtx.strokeStyle='#fff';mapCtx.lineWidth=2;mapCtx.stroke();mapCtx.fillStyle='#fff';mapCtx.font='700 9px Segoe UI';mapCtx.textAlign='center';mapCtx.textBaseline='middle';mapCtx.fillText(String(stop.sequence),q.x,q.y);});});
  }
  mapCanvas?.addEventListener('pointerdown',event=>{state.drag={x:event.clientX,y:event.clientY,panX:state.panX,panY:state.panY};mapCanvas.setPointerCapture(event.pointerId);});
  mapCanvas?.addEventListener('pointermove',event=>{if(!state.drag)return;state.panX=state.drag.panX+event.clientX-state.drag.x;state.panY=state.drag.panY+event.clientY-state.drag.y;drawMap();});
  mapCanvas?.addEventListener('pointerup',()=>{state.drag=null;});
  mapCanvas?.addEventListener('pointercancel',()=>{state.drag=null;});
  mapCanvas?.addEventListener('wheel',event=>{event.preventDefault();state.zoom=Math.max(2,Math.min(18,state.zoom+(event.deltaY<0?1:-1)));drawMap();},{passive:false});
  $('#total-map-reset')?.addEventListener('click',()=>{if(state.result){fitMap(state.result.solutions[state.selected]);drawMap();}});

  window.AxioTotalOptimization={enabled:()=>Boolean(checkbox?.checked),run,state};
})();
