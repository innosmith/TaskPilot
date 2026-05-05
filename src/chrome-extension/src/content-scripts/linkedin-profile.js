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

    // Profilbild im main-Bereich suchen (nicht im nav, wo das eigene Avatar ist)
    // LinkedIn CDN: URL auf _400_400 hochskalieren damit Pipedrive (min 128px) akzeptiert
    const img = mainEl.querySelector('img[src*="profile-displayphoto"]')
      || document.querySelector('main img[src*="profile-displayphoto"]');
    let profileImageUrl = '';
    if (img && img.src && img.src.startsWith('https://') && !img.src.includes('ghost')) {
      profileImageUrl = img.src.replace(/shrink_\d+_\d+/, 'shrink_400_400');
    }

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
