(() => {
  'use strict';

  const q = (selector, root = document) => root.querySelector(selector);
  const qa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const MAX_EDGE = 2400;
  const JPEG_QUALITY = 0.88;

  function showMessage(text, error = false) {
    const box = q('#dc-message');
    if (!box) return;
    box.textContent = text;
    box.className = `message ${error ? 'error' : 'success'}`;
    box.classList.remove('hidden');
  }

  function sideLabel(name) {
    return name === 'left_file' ? 'Document 1' : 'Document 2';
  }

  function safeFilename(name) {
    return String(name || 'photo').replace(/[^a-zA-Z0-9._-]+/g, '-');
  }

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('La photo ne peut pas être lue par ce navigateur.'));
      };
      image.src = url;
    });
  }

  async function normalizeCameraPhoto(file, targetName) {
    const image = await loadImage(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height));
    const width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale));
    const height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', {alpha: false});
    if (!context) throw new Error('La préparation de la photo a échoué.');
    context.drawImage(image, 0, 0, width, height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
    if (!blob) throw new Error('La conversion de la photo en JPEG a échoué.');
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    return new File([blob], `${safeFilename(targetName)}-${timestamp}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now()
    });
  }

  function assignFile(target, file) {
    if (typeof DataTransfer === 'undefined') {
      throw new Error('Ce navigateur ne permet pas encore de transférer la photo vers le formulaire.');
    }
    const transfer = new DataTransfer();
    transfer.items.add(file);
    target.files = transfer.files;
  }

  function clearPreview(wrapper) {
    const preview = q('.dc-camera-preview', wrapper);
    if (!preview) return;
    const oldUrl = preview.dataset.objectUrl;
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    preview.dataset.objectUrl = '';
    preview.innerHTML = '';
    preview.classList.add('dc-hidden');
  }

  function updateSelection(target, wrapper, source = 'file') {
    clearPreview(wrapper);
    const file = target.files?.[0];
    const status = q('.dc-camera-status', wrapper);
    if (!file) {
      status.textContent = 'Aucun document sélectionné.';
      status.classList.remove('has-file');
      return;
    }

    const sizeMb = file.size / (1024 * 1024);
    status.textContent = `${source === 'camera' ? 'Photo prête' : 'Fichier prêt'} : ${file.name} (${sizeMb.toLocaleString('fr-FR', {maximumFractionDigits: 1})} Mo)`;
    status.classList.add('has-file');

    if (file.type.startsWith('image/')) {
      const preview = q('.dc-camera-preview', wrapper);
      const url = URL.createObjectURL(file);
      preview.dataset.objectUrl = url;
      preview.innerHTML = `<img src="${url}" alt="Aperçu de ${sideLabel(target.name)}"><span>${source === 'camera' ? 'Photo prise avec l’appareil' : 'Image sélectionnée'}</span>`;
      preview.classList.remove('dc-hidden');
    }
  }

  function enhanceFileInput(target) {
    if (!target || target.dataset.dcCameraReady === '1') return false;
    target.dataset.dcCameraReady = '1';
    target.required = false;
    target.accept = '.pdf,.jpg,.jpeg,.png,image/jpeg,image/png';

    const sourceLabel = target.closest('label');
    if (!sourceLabel) return false;
    sourceLabel.classList.add('dc-file-source-label');

    const wrapper = document.createElement('div');
    wrapper.className = 'dc-camera-tools';
    wrapper.dataset.for = target.name;
    wrapper.innerHTML = `<div class="dc-camera-actions">
      <label class="dc-camera-button">
        <span class="dc-camera-icon" aria-hidden="true">📷</span>
        <span>Prendre une photo</span>
        <input type="file" accept="image/*" capture="environment" data-dc-camera-for="${target.name}" aria-label="Prendre une photo pour ${sideLabel(target.name)}">
      </label>
    </div>
    <small class="dc-camera-hint">Sur téléphone ou tablette, ce bouton ouvre directement l’appareil photo arrière.</small>
    <div class="dc-camera-status" role="status">Aucun document sélectionné.</div>
    <div class="dc-camera-preview dc-hidden"></div>`;
    sourceLabel.after(wrapper);

    const camera = q('[data-dc-camera-for]', wrapper);
    let assigningCamera = false;

    camera.addEventListener('change', async () => {
      const selected = camera.files?.[0];
      if (!selected) return;
      const status = q('.dc-camera-status', wrapper);
      status.textContent = 'Préparation de la photo…';
      status.classList.remove('has-file');
      try {
        const jpeg = await normalizeCameraPhoto(selected, target.name.replace('_file', ''));
        assigningCamera = true;
        assignFile(target, jpeg);
        assigningCamera = false;
        updateSelection(target, wrapper, 'camera');
      } catch (error) {
        assigningCamera = false;
        camera.value = '';
        updateSelection(target, wrapper);
        showMessage(error.message || String(error), true);
      }
    });

    target.addEventListener('change', () => {
      if (!assigningCamera) camera.value = '';
      updateSelection(target, wrapper, assigningCamera ? 'camera' : 'file');
    });
    return true;
  }

  function validateDocuments(event) {
    const form = event.currentTarget;
    const missing = ['left_file', 'right_file']
      .map(name => q(`input[name="${name}"]`, form))
      .filter(input => !input?.files?.length)
      .map(input => sideLabel(input?.name));
    if (!missing.length) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    showMessage(`Ajoutez un fichier ou prenez une photo pour : ${missing.join(' et ')}.`, true);
  }

  function enhanceDocumentForm() {
    const form = q('#dc-form');
    if (!form) return false;
    qa('input[type="file"][name="left_file"], input[type="file"][name="right_file"]', form).forEach(enhanceFileInput);
    if (form.dataset.dcCameraSubmitReady !== '1') {
      form.dataset.dcCameraSubmitReady = '1';
      form.addEventListener('submit', validateDocuments, {capture: true});
    }
    return true;
  }

  function init() {
    [0, 50, 200, 700, 1600].forEach(delay => window.setTimeout(enhanceDocumentForm, delay));
    const main = q('main');
    if (main && main.dataset.dcCameraObserver !== '1') {
      main.dataset.dcCameraObserver = '1';
      const observer = new MutationObserver(() => enhanceDocumentForm());
      observer.observe(main, {childList: true, subtree: true});
    }
  }

  window.AxioDocumentCamera = {
    enhance: enhanceDocumentForm,
    normalizeCameraPhoto
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
