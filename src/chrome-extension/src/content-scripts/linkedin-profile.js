/**
 * TaskPilot LinkedIn Sync – Content Script
 * Extrahiert Rohdaten aus LinkedIn /in/*-Seiten für LLM-Extraktion.
 *
 * Bewusst minimal gehalten: Strukturierte Datenextraktion (Name, Rolle,
 * Firma, Ort) übernimmt das LLM im Backend. Das Content Script liefert
 * nur den Seitentext, die URL und das Profilbild (via Canvas-to-Base64).
 *
 * Profilbild-Strategie:
 * 1. Aus eingebetteten LinkedIn Voyager-Daten (<code>-Tags) die grösste
 *    verfügbare Bild-URL extrahieren (800 > 400 > 200 > 100)
 * 2. Via hidden <img> laden (nutzt Browser-Session, kein CORS-Problem)
 * 3. Via Canvas zu Base64 konvertieren
 * 4. Fallback: Header-<img> direkt per Canvas exportieren
 */

(() => {
  'use strict';

  const SIZE_PRIORITY = [800, 400, 200, 100];

  function _findLargestPhotoUrl() {
    const candidates = new Map();

    for (const codeEl of document.querySelectorAll('code')) {
      const text = codeEl.textContent || '';
      if (!text.includes('profile-displayphoto')) continue;

      const urlPattern = /https:\/\/media\.licdn\.com\/dms\/image\/[^\s"'\\]+profile-displayphoto-shrink_(\d+)_(\d+)[^\s"'\\]*/g;
      let match;
      while ((match = urlPattern.exec(text)) !== null) {
        const size = parseInt(match[1], 10);
        const url = match[0]
          .replace(/\\u002F/g, '/')
          .replace(/\\u0026/g, '&')
          .replace(/\\u003D/g, '=')
          .replace(/\\/g, '');
        if (!candidates.has(size) || url.length > candidates.get(size).length) {
          candidates.set(size, url);
        }
      }
    }

    for (const size of SIZE_PRIORITY) {
      if (candidates.has(size)) return candidates.get(size);
    }
    return null;
  }

  function _loadImageAsBase64(url, timeoutMs = 5000) {
    return new Promise((resolve) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      const timer = setTimeout(() => { img.src = ''; resolve(null); }, timeoutMs);

      img.onload = () => {
        clearTimeout(timer);
        try {
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth;
          canvas.height = img.naturalHeight;
          canvas.getContext('2d').drawImage(img, 0, 0);
          resolve(canvas.toDataURL('image/jpeg', 0.92));
        } catch (_) {
          resolve(null);
        }
      };
      img.onerror = () => { clearTimeout(timer); resolve(null); };
      img.src = url;
    });
  }

  function _canvasFromElement(imgEl) {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = imgEl.naturalWidth;
      canvas.height = imgEl.naturalHeight;
      canvas.getContext('2d').drawImage(imgEl, 0, 0);
      return canvas.toDataURL('image/jpeg', 0.92);
    } catch (_) {
      return '';
    }
  }

  async function extractProfileData() {
    const mainEl = document.querySelector('main') || document.body;
    const pageText = (mainEl.innerText || '').substring(0, 50000);

    const headerImg = mainEl.querySelector('img[src*="profile-displayphoto"]')
      || document.querySelector('main img[src*="profile-displayphoto"]');

    let profileImageUrl = '';
    let profileImageBase64 = '';

    if (headerImg && headerImg.src && headerImg.src.startsWith('https://') && !headerImg.src.includes('ghost')) {
      profileImageUrl = headerImg.src;
    }

    const largeUrl = _findLargestPhotoUrl();

    if (largeUrl) {
      const base64 = await _loadImageAsBase64(largeUrl);
      if (base64) {
        profileImageBase64 = base64;
        profileImageUrl = largeUrl;
      }
    }

    if (!profileImageBase64 && headerImg && headerImg.complete && headerImg.naturalWidth > 0) {
      profileImageBase64 = _canvasFromElement(headerImg);
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
      extractProfileData()
        .then((data) => sendResponse({ success: true, data }))
        .catch((error) => sendResponse({ success: false, error: error.message }));
      return true;
    }
  });
})();
