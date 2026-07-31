(() => {
  'use strict';
  const token = new URLSearchParams(location.search).get('token') || '';
  let preview = null;
  const show = id => document.querySelectorAll('.activation-step').forEach(section => section.classList.toggle('active', section.id === id));
  const fail = message => { document.querySelector('#activation-error-message').textContent = message; show('activation-error'); };
  const json = async (url, options = {}) => {
    const response = await fetch(url, options); let body = null; try { body = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(body?.detail || `Erreur ${response.status}`); return body;
  };
  async function boot() {
    if (!token) return fail('Le lien d’activation est absent.');
    try {
      preview = await json(`/api/invitations/preview?token=${encodeURIComponent(token)}`);
      document.querySelector('#activation-recipient').textContent = `${preview.user.first_name} ${preview.user.last_name}, vous avez été invité à rejoindre ${preview.company.name}.`;
      show('activation-password');
    } catch (error) { fail(error.message || String(error)); }
  }
  document.querySelector('#activation-password-form').addEventListener('submit', async event => {
    event.preventDefault(); const password = document.querySelector('#activation-password-input').value; const confirmation = document.querySelector('#activation-password-confirm').value;
    if (password !== confirmation) return fail('Les deux mots de passe ne correspondent pas.');
    try {
      const result = await json('/api/invitations/activate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,password})});
      if (result.needs_company_profile) {
        document.querySelector('[name="legal_name"]').value = preview.company.name;
        document.querySelector('[name="contact_first_name"]').value = preview.user.first_name;
        document.querySelector('[name="contact_last_name"]').value = preview.user.last_name;
        document.querySelector('[name="contact_email"]').value = preview.user.email;
        show('activation-profile');
      } else location.href = '/';
    } catch (error) { fail(error.message || String(error)); }
  });
  document.querySelector('#activation-profile-form').addEventListener('submit', async event => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget));
    try { await json('/api/company/profile', {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); show('activation-success'); }
    catch (error) { fail(error.message || String(error)); }
  });
  boot();
})();
