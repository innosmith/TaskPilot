/**
 * TaskPilot LinkedIn Sync – Content Script
 * Extrahiert Rohdaten aus LinkedIn /in/*-Seiten für LLM-Extraktion.
 *
 * Bewusst minimal gehalten: Strukturierte Datenextraktion (Name, Rolle,
 * Firma, Ort) übernimmt das LLM im Backend. Das Content Script liefert
 * nur den Seitentext, die URL und die Profilbild-URL (CDN-Muster).
 */

(() => {
  'use strict';

  function extractProfileData() {
    const mainEl = document.querySelector('main') || document.body;
    const pageText = (mainEl.innerText || '').substring(0, 50000);

    const img = document.querySelector('img[src*="profile-displayphoto"]');
    const profileImageUrl = (img && img.src && img.src.startsWith('https://') && !img.src.includes('ghost'))
      ? img.src : '';

    return {
      linkedinUrl: window.location.href.split('?')[0].replace(/\/+$/, ''),
      profileImageUrl,
      pageText,
    };
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.action === 'extractProfile') {
      try {
        sendResponse({ success: true, data: extractProfileData() });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    }
    return true;
  });
})();
