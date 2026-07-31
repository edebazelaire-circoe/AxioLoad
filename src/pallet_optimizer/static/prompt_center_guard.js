(() => {
  'use strict';
  const nativeRemove = Element.prototype.remove;
  Element.prototype.remove = function removeElement() {
    if (this.matches?.('[data-admin-view="document-prompts"]')) {
      this.hidden = true;
      this.classList.add('hidden');
      this.setAttribute('aria-hidden', 'true');
      return;
    }
    return nativeRemove.call(this);
  };
})();
