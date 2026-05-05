/**
 * TaskPilot LinkedIn Sync – Content Script
 * Extrahiert Rohdaten aus LinkedIn /in/*-Seiten für LLM-Extraktion.
 *
 * Bewusst minimal gehalten: Strukturierte Datenextraktion (Name, Rolle,
 * Firma, Ort) übernimmt das LLM im Backend. Das Content Script liefert
 * nur den Seitentext, die URL und das Profilbild (via Canvas-to-Base64).
 */

(() => {
  'use strict';

  function extractProfileData() {
    const mainEl = document.querySelector('main') || document.body;
    const pageText = (mainEl.innerText || '').substring(0, 50000);

    const img = mainEl.querySelector('img[src*="profile-displayphoto"]')
      || document.querySelector('main img[src*="profile-displayphoto"]');

    let profileImageUrl = '';
    let profileImageBase64 = '';

    if (img && img.src && img.src.startsWith('https://') && !img.src.includes('ghost')) {
      profileImageUrl = img.src;

      if (img.complete && img.naturalWidth > 0) {
        try {
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          canvas.getContext('2d').drawImage(img, 0, 0);
          profileImageBase64 = canvas.toDataURL('image/jpeg', 0.9);
        } catch (_) { /* CORS-tainted canvas, Base64 nicht verfügbar */ }
      }
    }

    return {
      linkedinUrl: window.location.href.split('?')[0].replace(/\/+$/, ''),
      profileImageUrl,
      profileImageBase64,
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
