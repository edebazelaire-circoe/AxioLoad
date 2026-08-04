(() => {
  'use strict';

  function removeDuplicatePromptSettings() {
    document.querySelector('#dc-prompt-settings')?.remove();
  }

  function keepDesktopSettings() {
    const settings = document.querySelector('#tab-settings');
    if (settings) settings.dataset.desktopWorkspace = '1';
    removeDuplicatePromptSettings();
  }

  function scheduleCleanup() {
    [0, 40, 160, 500].forEach(delay => window.setTimeout(keepDesktopSettings, delay));
  }

  document.addEventListener('click', event => {
    if (event.target.closest?.('#open-settings, [data-workspace], [data-workspace-tab="prompts"]')) {
      scheduleCleanup();
    }
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scheduleCleanup, {once: true});
  } else {
    scheduleCleanup();
  }
})();
