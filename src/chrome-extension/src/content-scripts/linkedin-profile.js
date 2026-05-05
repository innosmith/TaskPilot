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

  // ── Topcard ──────────────────────────────────────────────

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

  // ── Name ─────────────────────────────────────────────────

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

  // ── Headline ─────────────────────────────────────────────

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
            if (text && text.length > 5 && text !== name && !_isLocationLike(text)) {
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
      if (text && text.length > 15 && text !== name &&
          !_isLocationLike(text) && !_isConnectionCount(text)) {
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

  // ── Location ─────────────────────────────────────────────

  const LOCATION_BLACKLIST = /^(herr|frau|mr\.?|mrs?\.?|dr\.?|prof\.?|kontaktinformation|contact\s*info|mehr\s*anzeigen|show\s*more|verbindungen|connections)/i;

  function _isLocationLike(text) {
    if (LOCATION_BLACKLIST.test(text)) return false;
    return (
      text.length < 50 &&
      text.length > 2 &&
      (/^[A-ZÄÖÜ][a-zäöüéèê]+(?:[,\s]+[A-ZÄÖÜ].*)?$/.test(text) ||
        /\b(Schweiz|Deutschland|Österreich|France|Italy|United|Germany|Austria|Suisse|Svizzera)\b/i.test(text))
    );
  }

  function _isConnectionCount(text) {
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
            if (text && text.length < 60 && _isLocationLike(text)) return text;
          }
        }
      }
    }

    const paragraphs = topcard.querySelectorAll('p');
    for (const p of paragraphs) {
      const text = p.innerText.trim();
      if (text && _isLocationLike(text)) return text;
    }

    const spans = topcard.querySelectorAll('span');
    for (const span of spans) {
      if (span.children.length > 0) continue;
      const text = span.innerText.trim();
      if (text && _isLocationLike(text)) return text;
    }

    return '';
  }

  // ── Profilbild ───────────────────────────────────────────

  function extractProfileImage() {
    const highPriority = document.querySelector(
      'img[src*="profile-displayphoto"][fetchpriority="high"]'
    );
    if (highPriority && _isValidImageSrc(highPriority.src)) return highPriority.src;

    const displayPhoto = document.querySelector('img[src*="profile-displayphoto"]');
    if (displayPhoto && _isValidImageSrc(displayPhoto.src)) return displayPhoto.src;

    const topcard = findTopcardSection();
    const topcardImg = topcard.querySelector('img[src*="profile-displayphoto"]');
    if (topcardImg && _isValidImageSrc(topcardImg.src)) return topcardImg.src;

    const figureImg = topcard.querySelector('figure img[src^="https://"]');
    if (figureImg && _isValidImageSrc(figureImg.src)) return figureImg.src;

    const allImages = document.querySelectorAll('img[src*="profile-displayphoto"]');
    for (const img of allImages) {
      if (_isValidImageSrc(img.src) && img.src.includes('_400_400')) return img.src;
    }
    for (const img of allImages) {
      if (_isValidImageSrc(img.src)) return img.src;
    }

    return '';
  }

  function _isValidImageSrc(src) {
    return src && src.startsWith('https://') && !src.includes('ghost');
  }

  function extractLinkedInUrl() {
    return window.location.href.split('?')[0].replace(/\/+$/, '');
  }

  // ── Experience-Section finden (multi-strategy) ───────────

  function _findExperienceSection() {
    const strategies = [
      () => document.querySelector('[id="experience"]'),
      () => document.querySelector('#experience'),
      () => document.querySelector('section[id*="experience" i]'),
      () => document.querySelector('[data-section="experience"]'),
    ];

    for (const strategy of strategies) {
      try {
        const el = strategy();
        if (el) {
          return el.closest('section') || el.parentElement;
        }
      } catch (_) { /* weiter */ }
    }

    const headingTerms = ['experience', 'berufserfahrung', 'expérience', 'esperienza'];
    const headings = document.querySelectorAll('h2, h3, [role="heading"]');
    for (const h of headings) {
      const text = (h.innerText || h.textContent || '').trim().toLowerCase();
      if (headingTerms.some(term => text.includes(term))) {
        return h.closest('section') || h.parentElement?.parentElement;
      }
    }

    const sections = document.querySelectorAll('main section');
    for (const sec of sections) {
      const links = sec.querySelectorAll('a[href*="/company/"]');
      if (links.length >= 1) {
        const text = sec.innerText || '';
        if (/\d{4}/.test(text) && /(–|—|-|bis|present|heute|current)/i.test(text)) {
          return sec;
        }
      }
    }

    return null;
  }

  // ── Experience-Positionen extrahieren ────────────────────

  function extractExperiencePositions() {
    const positions = [];
    try {
      const section = _findExperienceSection();
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
      company = companyLink.innerText.trim();
    }

    const visibleText = item.innerText || '';
    const lines = visibleText.split('\n').map(l => l.trim()).filter(l => l.length > 0);

    for (const line of lines) {
      if (_isTimeRange(line)) {
        if (!timeRange) timeRange = line;
        continue;
      }
      if (_isDuration(line)) continue;
      if (_isMetaText(line)) continue;
      if (line === company) continue;

      if (line.includes('·')) {
        const parts = line.split('·').map(p => p.trim());
        if (!company && parts[0]) company = parts[0];
        continue;
      }

      if (!title && line.length > 2 && line.length < 150) {
        title = line;
      }
    }

    return { title, company, timeRange };
  }

  function _isTimeRange(text) {
    return /\b(jan|feb|m[aä]r|apr|ma[iy]|jun[ei]?|jul[iy]?|aug|sep|okt|oct|nov|dez|dec|heute|present|current|actualité)/i.test(text) &&
           /\d{4}/.test(text);
  }

  function _isDuration(text) {
    return /^\d+\s*(Jahr|Monat|Mon\.|yr|mo|year|month|an|mois)/i.test(text);
  }

  function _isMetaText(text) {
    return /^(Vollzeit|Teilzeit|Full-time|Part-time|Contract|Freelance|Selbstständig|Self-employed|Befristete|Saisonal|Internship|Apprentice|Praktik)/i.test(text) ||
           /^\d+[\s.]*(Mitarbeiter|employees|Beschäftigte)/i.test(text) ||
           /^(Kompetenzen|Skills|Fähigkeiten):/i.test(text);
  }

  // ── Firmen aus Positionen + Topcard-Fallback ─────────────

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
        const text = link.innerText.trim();
        if (text && text.length > 1 && text.length < 100 && !companies.includes(text)) {
          companies.push(text);
        }
      }
    }

    return companies;
  }

  // ── Haupt-Extraktion ────────────────────────────────────

  function extractProfileData() {
    const name = extractName();
    const headline = extractHeadline();
    const positions = extractExperiencePositions();
    const currentPosition = positions.length > 0 ? positions[0] : null;
    const experienceCompanies = extractCompaniesFromPositions(positions);

    const expSection = _findExperienceSection();
    const _debug = {
      experienceSectionFound: !!expSection,
      experiencePositionCount: positions.length,
      sectionSearchMethod: _debugSectionMethod(),
    };

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
      _debug,
    };

    const needsLlmFallback = !currentPosition || !currentPosition.title || !currentPosition.company;
    if (needsLlmFallback) {
      try {
        const mainEl = document.querySelector('main') || document.body;
        const html = mainEl.innerText || '';
        if (html.length > 200) {
          result.fallbackHtml = html.substring(0, 50000);
          result._debug.fallbackHtmlLength = result.fallbackHtml.length;
        }
      } catch (_) { /* HTML-Extraktion optional */ }
    }

    return result;
  }

  function _debugSectionMethod() {
    if (document.querySelector('[id="experience"]')) return 'id=experience';
    if (document.querySelector('#experience')) return '#experience';
    if (document.querySelector('section[id*="experience" i]')) return 'section[id*=experience]';
    if (document.querySelector('[data-section="experience"]')) return 'data-section';
    const headings = document.querySelectorAll('h2, h3, [role="heading"]');
    for (const h of headings) {
      const text = (h.innerText || '').trim().toLowerCase();
      if (text.includes('experience') || text.includes('berufserfahrung')) {
        return `heading: "${h.innerText.trim()}"`;
      }
    }
    const sections = document.querySelectorAll('main section');
    for (const sec of sections) {
      const links = sec.querySelectorAll('a[href*="/company/"]');
      if (links.length >= 1) {
        const text = sec.innerText || '';
        if (/\d{4}/.test(text) && /(–|—|-|bis|present|heute|current)/i.test(text)) {
          return 'company-links-heuristic';
        }
      }
    }
    return 'NICHT GEFUNDEN';
  }

  // ── Message Handler ──────────────────────────────────────

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
