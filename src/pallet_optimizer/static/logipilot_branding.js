(() => {
  'use strict';

  const BRAND_NAME = 'LogiPilot';
  const TAGLINE = 'Optimisation physique du chargement, planification d’itinéraires et contrôle documentaire.';
  const LOGO = '/static/brand/logipilot-horizontal-dark.svg';
  const ICON = '/static/brand/logipilot-icon.svg';

  function replaceBrandText(root = document.body) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return node.nodeValue?.includes('AxioLoad') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => { node.nodeValue = node.nodeValue.replaceAll('AxioLoad', BRAND_NAME); });
  }

  function updateAttributes(root = document) {
    root.querySelectorAll?.('[alt], [title], [aria-label]').forEach(element => {
      ['alt', 'title', 'aria-label'].forEach(attribute => {
        const value = element.getAttribute(attribute);
        if (value?.includes('AxioLoad')) element.setAttribute(attribute, value.replaceAll('AxioLoad', BRAND_NAME));
      });
    });
  }

  function installFavicon() {
    document.querySelectorAll('link[rel~="icon"]').forEach(link => link.remove());
    const link = document.createElement('link');
    link.rel = 'icon';
    link.type = 'image/svg+xml';
    link.href = ICON;
    document.head.append(link);
  }

  function applyBranding() {
    document.title = `${BRAND_NAME} · Pilotage logistique`;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '#0F3D3E');
    installFavicon();

    const logo = document.querySelector('.brand-logo');
    if (logo) {
      logo.src = LOGO;
      logo.alt = BRAND_NAME;
      logo.width = 330;
      logo.height = 78;
    }

    const eyebrow = document.querySelector('.brand-lockup .eyebrow');
    if (eyebrow) eyebrow.textContent = 'Logiciel d’optimisation de transport';
    const tagline = document.querySelector('.brand-lockup p');
    if (tagline) tagline.textContent = TAGLINE;

    replaceBrandText();
    updateAttributes();
  }

  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      replaceBrandText(node);
      updateAttributes(node);
    }));
  });

  function init() {
    applyBranding();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
