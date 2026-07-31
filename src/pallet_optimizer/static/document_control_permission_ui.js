(() => {
  'use strict';

  function install() {
    const documentTab = document.querySelector('[data-tab="document-control"]');
    const switcher = document.querySelector('#workspace-switcher');
    const documentWorkspace = switcher?.querySelector('[data-workspace="documents"]');
    const databaseWorkspace = switcher?.querySelector('[data-workspace="database"]');
    const optimizationWorkspace = switcher?.querySelector('[data-workspace="optimization"]');
    if (!documentTab || !switcher || !documentWorkspace) return false;
    if (documentWorkspace.dataset.permissionBound === '1') return true;

    documentWorkspace.dataset.permissionBound = '1';
    const sync = () => {
      const denied = documentTab.hidden || documentTab.hasAttribute('hidden');
      documentWorkspace.hidden = denied;
      const visibleCount = [databaseWorkspace, optimizationWorkspace, documentWorkspace]
        .filter(button => button && !button.hidden).length;
      switcher.dataset.visibleCount = String(visibleCount);
      switcher.classList.toggle('single-workspace', visibleCount === 1);
      if (denied && document.body.dataset.workspace === 'documents') {
        const fallback = [optimizationWorkspace, databaseWorkspace]
          .find(button => button && !button.hidden && !button.disabled);
        fallback?.click();
      }
    };
    new MutationObserver(sync).observe(documentTab, {attributes: true, attributeFilter: ['hidden']});
    sync();
    return true;
  }

  const run = () => {
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(install, delay));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, {once: true});
  else run();
})();
