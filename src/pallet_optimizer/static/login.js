(() => {
  'use strict';
  const form = document.querySelector('#login-form');
  const message = document.querySelector('#login-message');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    message.classList.add('hidden');
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(form));
      const response = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Connexion impossible');
      location.href = '/';
    } catch (error) {
      message.textContent = error.message || String(error);
      message.className = 'message error';
      message.classList.remove('hidden');
    } finally { button.disabled = false; }
  });
})();
