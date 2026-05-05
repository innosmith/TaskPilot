/**
 * TaskPilot LinkedIn Sync – Content Script
 * Extrahiert Profildaten aus LinkedIn /in/*-Seiten.
 *
 * LinkedIn nutzt obfuskierte CSS-Klassen, die sich häufig ändern.
 * Deshalb setzen wir auf strukturelle Selektoren, data-Attribute,
 * aria-Labels und bekannte URL-Muster statt fragiler Klassennamen.
 */

(() => {
  'use strict';

  /**
   * Findet die Topcard-Section – das Hauptprofil-Element oben auf der Seite.
   * Sucht nach section[data-member-id], section mit "Topcard" im componentkey,
   * oder fällt auf die erste grosse Section zurück.
   */
  function findTopcardSection() {
    const byMemberId = document.querySelector('section[data-member-id]');
    if (byMemberId) return byMemberId;

    const byComponentKey = document.querySelector('section[componentkey*="Topcard" i]');
    if (byComponentKey) return byComponentKey;

    const byTestId = document.querySelector('[data-testid="profile-topcard"]');
    if (byTestId) return byTestId;

    const mainContent = document.querySelector('main') || document.body;
    const firstSection = mainContent.querySelector('section');
    if (firstSection) return firstSection;

    return document.body;
  }

  function extractName() {
    const titleTag = document.querySelector('title');
    if (titleTag) {
      const titleText = titleTag.textContent.trim();
      const match = titleText.match(/^(.+?)\s*[|\u2013\u2014–—]\s*LinkedIn/);
      if (match && match[1].trim().length > 1) {
        return match[1].trim();
      }
    }

    const topcard = findTopcardSection();

    const h2 = topcard.querySelector('h2');
    if (h2) {
      const text = h2.innerText.trim();
      if (text && text.length > 1 && !text.toLowerCase().includes('linkedin')) return text;
    }

    const h1 = topcard.querySelector('h1');
    if (h1) {
      const text = h1.innerText.trim();
      if (text && text.length > 1) return text;
    }

    const h1Global = document.querySelector('h1');
    if (h1Global) return h1Global.innerText.trim();

    return '';
  }

  function extractHeadline() {
    const topcard = findTopcardSection();
    const name = extractName();

    const nameHeading = topcard.querySelector('h1') || topcard.querySelector('h2');
    if (nameHeading) {
      let cursor = nameHeading.parentElement;
      while (cursor && cursor !== topcard) {
        let sibling = cursor.nextElementSibling;
        while (sibling) {
          const p = sibling.matches('p') ? sibling : sibling.querySelector('p');
          if (p) {
            const text = p.innerText.trim();
            if (text && text.length > 5 && text !== name && !isLocationLike(text)) {
              return text;
            }
          }
          sibling = sibling.nextElementSibling;
        }
        cursor = cursor.parentElement;
      }
    }

    const allParagraphs = topcard.querySelectorAll('p');
    for (const p of allParagraphs) {
      const text = p.innerText.trim();
      if (
        text &&
        text.length > 15 &&
        text !== name &&
        !isLocationLike(text) &&
        !isConnectionCount(text)
      ) {
        return text;
      }
    }

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      const content = metaDesc.getAttribute('content') || '';
      const cleaned = content.replace(/^.*?[–—-]\s*/, '').trim();
      if (cleaned && cleaned.length > 10) return cleaned;
    }

    return '';
  }

  function isLocationLike(text) {
    return (
      text.length < 40 &&
      (/^[A-ZÄÖÜ][a-zäöüß]+(?:,\s*[A-ZÄÖÜ].*)?$/.test(text) ||
        /^Schweiz|Deutschland|Österreich|France|Italy|United|Germany|Austria/i.test(text))
    );
  }

  function isConnectionCount(text) {
    return /\d+[\s+]*(?:Kontakte|Follower|connections|followers)/i.test(text);
  }

  function extractLocation() {
    const topcard = findTopcardSection();

    const contactLink = topcard.querySelector('a[href*="contact-info"], a[href*="overlay/contact"]');
    if (contactLink) {
      let container = contactLink.closest('div') || contactLink.parentElement;
      if (container) {
        const sibling = container.previousElementSibling;
        if (sibling) {
          const p = sibling.matches('p') ? sibling : sibling.querySelector('p');
          if (p) {
            const text = p.innerText.trim();
            if (text && text.length < 60 && isLocationLike(text)) return text;
          }
        }
      }
    }

    const paragraphs = topcard.querySelectorAll('p');
    for (const p of paragraphs) {
      const text = p.innerText.trim();
      if (text && isLocationLike(text)) return text;
    }

    const spans = topcard.querySelectorAll('span');
    for (const span of spans) {
      if (span.children.length > 0) continue;
      const text = span.innerText.trim();
      if (text && isLocationLike(text)) return text;
    }

    return '';
  }

  function extractProfileImage() {
    const highPriority = document.querySelector(
      'img[src*="profile-displayphoto"][fetchpriority="high"]'
    );
    if (highPriority && isValidImageSrc(highPriority.src)) return highPriority.src;

    const displayPhoto = document.querySelector('img[src*="profile-displayphoto"]');
    if (displayPhoto && isValidImageSrc(displayPhoto.src)) return displayPhoto.src;

    const topcard = findTopcardSection();
    const topcardImg = topcard.querySelector('img[src*="profile-displayphoto"]');
    if (topcardImg && isValidImageSrc(topcardImg.src)) return topcardImg.src;

    const figureImg = topcard.querySelector('figure img[src^="https://"]');
    if (figureImg && isValidImageSrc(figureImg.src)) return figureImg.src;

    const allImages = document.querySelectorAll('img[src*="profile-displayphoto"]');
    for (const img of allImages) {
      if (isValidImageSrc(img.src) && img.src.includes('_400_400')) return img.src;
    }
    for (const img of allImages) {
      if (isValidImageSrc(img.src)) return img.src;
    }

    const legacySelectors = [
      'img.pv-top-card-profile-picture__image--show',
      'img.pv-top-card-profile-picture__image',
      '.pv-top-card__photo img',
    ];
    for (const sel of legacySelectors) {
      const img = document.querySelector(sel);
      if (img && isValidImageSrc(img.src)) return img.src;
    }

    return '';
  }

  function isValidImageSrc(src) {
    return src && src.startsWith('https://') && !src.includes('ghost');
  }

  function extractLinkedInUrl() {
    return window.location.href.split('?')[0].replace(/\/+$/, '');
  }

  /**
   * Extrahiert die aktuelle(n) Position(en) aus der Experience-Section.
   * Gibt ein Array von { title, company, timeRange } zurück.
   * Der erste Eintrag ist die aktuellste Position.
   */
  function extractExperiencePositions() {
    const positions = [];
    try {
      const experienceAnchor = document.querySelector('[id="experience"]');
      if (!experienceAnchor) return positions;

      const section = experienceAnchor.closest('section') || experienceAnchor.parentElement;
      if (!section) return positions;

      const list = section.querySelector('ul');
      if (!list) return positions;

      const items = list.querySelectorAll(':scope > li');
      for (const item of items) {
        try {
          const pos = _parseExperienceItem(item);
          if (pos && (pos.title || pos.company)) {
            positions.push(pos);
          }
        } catch (_) { /* Eintrag überspringen */ }
      }
    } catch (_) { /* Experience-Section nicht verfügbar */ }
    return positions;
  }

  function _parseExperienceItem(item) {
    let company = '';
    let title = '';
    let timeRange = '';

    const companyLink = item.querySelector('a[href*="/company/"], a[href*="/school/"]');
    if (companyLink) {
      const linkText = companyLink.querySelector('span') || companyLink;
      company = linkText.innerText.trim();
    }

    const leafSpans = [];
    for (const span of item.querySelectorAll('span')) {
      if (span.children.length === 0 && span.offsetParent !== null) {
        const text = span.innerText.trim();
        if (text) leafSpans.push(text);
      }
    }

    for (const text of leafSpans) {
      if (_isTimeRange(text)) {
        if (!timeRange) timeRange = text;
        continue;
      }
      if (text === company) continue;
      if (text.includes('·')) {
        const parts = text.split('·').map(p => p.trim());
        if (!company) company = parts[0];
        continue;
      }
      if (!title && text.length > 2 && text.length < 120 &&
          !_isTimeRange(text) && !_isDuration(text) && !_isMetaText(text)) {
        title = text;
      }
    }

    if (!title) {
      const visibleText = item.innerText || '';
      const lines = visibleText.split('\n').map(l => l.trim()).filter(l =>
        l.length > 2 && l.length < 120 &&
        l !== company && !_isTimeRange(l) && !_isDuration(l) && !_isMetaText(l)
      );
      if (lines.length > 0) title = lines[0];
    }

    return { title, company, timeRange };
  }

  function _isTimeRange(text) {
    return /\b(jan|feb|mär|apr|mai|jun|jul|aug|sep|okt|nov|dez|heute|present|current|bis|–|–)/i.test(text) &&
           /\d{4}/.test(text);
  }

  function _isDuration(text) {
    return /^\d+\s*(Jahr|Monat|Mon\.|yr|mo)/i.test(text);
  }

  function _isMetaText(text) {
    return /^(Vollzeit|Teilzeit|Full-time|Part-time|Contract|Freelance|Selbstständig|Self-employed)/i.test(text) ||
           /^\d+\s*(Mitarbeiter|employees)/i.test(text);
  }

  /**
   * Extrahiert Firmennamen aus vorberechneten Positionen,
   * mit Topcard-Links als Fallback.
   */
  function extractCompaniesFromPositions(positions) {
    const companies = [];

    for (const pos of positions) {
      if (pos.company && !companies.includes(pos.company)) {
        companies.push(pos.company);
      }
    }

    if (companies.length === 0) {
      const topcard = findTopcardSection();
      const companyLinks = topcard.querySelectorAll(
        'a[href*="/company/"], a[href*="/school/"]'
      );
      for (const link of companyLinks) {
        const textEl = link.querySelector('p') || link.querySelector('span') || link;
        const text = textEl.innerText.trim();
        if (text && text.length > 1 && text.length < 100 && !companies.includes(text)) {
          companies.push(text);
        }
      }
    }

    return companies;
  }

  function extractProfileData() {
    const name = extractName();
    const headline = extractHeadline();
    const positions = extractExperiencePositions();
    const currentPosition = positions.length > 0 ? positions[0] : null;
    const experienceCompanies = extractCompaniesFromPositions(positions);

    const result = {
      name,
      headline,
      jobTitle: currentPosition ? currentPosition.title : '',
      company: currentPosition ? currentPosition.company : '',
      location: extractLocation(),
      profileImageUrl: extractProfileImage(),
      linkedinUrl: extractLinkedInUrl(),
      experienceCompanies,
      currentPosition: currentPosition || { title: '', company: '', timeRange: '' },
      allPositions: positions,
    };

    const heuristicComplete = !!(name && name.length > 1 && headline && headline.length > 3);
    if (!heuristicComplete) {
      try {
        const topcard = findTopcardSection();
        const html = topcard ? topcard.outerHTML : '';
        if (html && html.length > 100) {
          result.fallbackHtml = html.substring(0, 200000);
        }
      } catch (_) { /* HTML-Extraktion optional */ }
    }

    return result;
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.action === 'extractProfile') {
      try {
        const data = extractProfileData();
        sendResponse({ success: true, data });
      } catch (error) {
        sendResponse({ success: false, error: error.message });
      }
    }
    return true;
  });
})();
