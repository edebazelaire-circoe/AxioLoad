(() => {
  'use strict';

  const initializeAdminPanel = () => {
    if (document.querySelector('#open-admin')) return;

    const topbar = document.querySelector('.topbar');
    const settingsButton = document.querySelector('#open-settings');
    const main = document.querySelector('main');
    if (!topbar || !settingsButton || !main) return;

    const style = document.createElement('style');
    style.id = 'admin-panel-styles';
    style.textContent = `
      .topbar-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex:none}
      .admin-access{border-color:rgba(0,168,191,.58)}
      .admin-access:hover,.admin-access.active{background:rgba(0,168,191,.22);border-color:#9DE3C2}
      .admin-page{max-width:1180px;margin:0 auto}
      .admin-heading{align-items:center}
      .admin-placeholder{display:grid;grid-template-columns:auto minmax(0,1fr);gap:20px;align-items:center;min-height:260px;padding:32px;border:1px dashed var(--line-strong);border-radius:16px;background:linear-gradient(135deg,var(--surface-2),var(--paper))}
      .admin-placeholder-icon{display:grid;place-items:center;width:68px;height:68px;border-radius:18px;background:var(--accent2);color:var(--accent)}
      .admin-placeholder-icon svg{width:34px;height:34px;fill:currentColor}
      .admin-placeholder h3{margin:0 0 8px;font-size:20px}
      .admin-placeholder p{max-width:720px;margin:0;color:var(--muted)}
      .admin-status{display:inline-flex;align-items:center;margin-top:18px;padding:6px 10px;border:1px solid var(--accent2-border);border-radius:999px;background:var(--accent2);color:var(--accent);font-size:12px;font-weight:800}
      #admin-title:focus{outline:none}
      @media(max-width:650px){
        .topbar-actions{gap:6px}
        .admin-placeholder{grid-template-columns:1fr;min-height:0;padding:22px}
        .admin-placeholder-icon{width:56px;height:56px}
      }
    `;
    document.head.append(style);

    const actions = document.createElement('div');
    actions.className = 'topbar-actions';
    settingsButton.before(actions);
    actions.append(settingsButton);

    const adminButton = document.createElement('button');
    adminButton.id = 'open-admin';
    adminButton.className = 'settings-access admin-access';
    adminButton.type = 'button';
    adminButton.setAttribute('aria-controls', 'tab-admin');
    adminButton.setAttribute('aria-label', 'Ouvrir la configuration administrateur');
    adminButton.setAttribute('aria-expanded', 'false');
    adminButton.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4.5 5.2v5.9c0 4.8 3.1 9.2 7.5 10.9 4.4-1.7 7.5-6.1 7.5-10.9V5.2L12 2Zm0 4.1a2.7 2.7 0 1 1 0 5.4 2.7 2.7 0 0 1 0-5.4Zm4.2 10.4H7.8v-.7c0-1.9 2.8-3 4.2-3s4.2 1.1 4.2 3v.7Z"/></svg>
      <span>Admin</span>
    `;
    actions.prepend(adminButton);

    const panel = document.createElement('section');
    panel.id = 'tab-admin';
    panel.className = 'panel tab-panel admin-page';
    panel.setAttribute('aria-labelledby', 'admin-title');
    panel.innerHTML = `
      <div class="panel-heading admin-heading">
        <div>
          <div class="eyebrow">Administration</div>
          <h2 id="admin-title" tabindex="-1">Configuration administrateur</h2>
          <p class="section-intro">Cet espace accueillera les futurs paramètres de gestion et d’administration d’AxioLoad.</p>
        </div>
        <button id="close-admin" class="secondary" type="button">Retour à l’application</button>
      </div>
      <section class="admin-placeholder" aria-labelledby="admin-placeholder-title">
        <div class="admin-placeholder-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 2 4.5 5.2v5.9c0 4.8 3.1 9.2 7.5 10.9 4.4-1.7 7.5-6.1 7.5-10.9V5.2L12 2Zm0 4.1a2.7 2.7 0 1 1 0 5.4 2.7 2.7 0 0 1 0-5.4Zm4.2 10.4H7.8v-.7c0-1.9 2.8-3 4.2-3s4.2 1.1 4.2 3v.7Z"/></svg>
        </div>
        <div>
          <h3 id="admin-placeholder-title">Panneau prêt à être configuré</h3>
          <p>La structure de navigation est en place. Les futurs réglages administrateur pourront être ajoutés ici sans mélanger les préférences utilisateur et les fonctions de gestion.</p>
          <span class="admin-status">Configuration à venir</span>
        </div>
      </section>
    `;
    main.append(panel);

    let previousTab = document.querySelector('.tab.active')?.dataset.tab || 'vehicles';

    const setAdminState = active => {
      adminButton.classList.toggle('active', active);
      adminButton.setAttribute('aria-expanded', active ? 'true' : 'false');
    };

    const rememberMainTab = () => {
      const activeTab = document.querySelector('.tab.active')?.dataset.tab;
      if (activeTab) previousTab = activeTab;
    };

    const openAdmin = () => {
      rememberMainTab();
      document.querySelectorAll('.tab').forEach(button => button.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(tabPanel => tabPanel.classList.remove('active'));
      settingsButton.classList.remove('active');
      panel.classList.add('active');
      setAdminState(true);
      document.querySelector('#admin-title')?.focus();
    };

    const closeAdmin = () => {
      panel.classList.remove('active');
      setAdminState(false);
      if (typeof switchTab === 'function') {
        switchTab(previousTab);
      } else {
        document.querySelector(`[data-tab="${previousTab}"]`)?.classList.add('active');
        document.querySelector(`#tab-${previousTab}`)?.classList.add('active');
      }
    };

    adminButton.addEventListener('click', openAdmin);
    panel.querySelector('#close-admin').addEventListener('click', closeAdmin);

    document.querySelectorAll('.tab').forEach(button => {
      button.addEventListener('click', () => {
        previousTab = button.dataset.tab || previousTab;
        panel.classList.remove('active');
        setAdminState(false);
      });
    });

    settingsButton.addEventListener('click', () => {
      panel.classList.remove('active');
      setAdminState(false);
    });

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && panel.classList.contains('active')) closeAdmin();
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAdminPanel, { once: true });
  } else {
    initializeAdminPanel();
  }
})();
