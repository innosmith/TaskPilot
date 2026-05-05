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

  function parseHeadline(headline) {
    if (!headline) return { jobTitle: '', company: '' };
    const atPatterns = [
      /^(.+?)\s+(?:bei|at|@|chez|à)\s+(.+)$/i,
      /^(.+?)\s*[|–—-]\s*(.+)$/,
    ];
    for (const pattern of atPatterns) {
      const match = headline.match(pattern);
      if (match) {
        return { jobTitle: match[1].trim(), company: match[2].trim() };
      }
    }
    return { jobTitle: headline, company: '' };
  }

  /**
   * Extrahiert Firmennamen aus der Topcard-Rechtspalte.
   * LinkedIn zeigt dort die aktuellen Positionen als kompakte Links.
   */
  function extractExperienceCompanies() {
    const companies = [];
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

    if (companies.length === 0) {
      try {
        const experienceSection = document.querySelector('[id="experience"]');
        if (experienceSection) {
          const list =
            experienceSection.parentElement?.querySelector('ul') ||
            experienceSection.closest('section')?.querySelector('ul');
          if (list) {
            const items = list.querySelectorAll(':scope > li');
            items.forEach((item) => {
              try {
                const link = item.querySelector('a[href*="/company/"], a[href*="/school/"]');
                if (link) {
                  const name = (link.querySelector('span') || link).innerText.trim();
                  if (name && !companies.includes(name)) companies.push(name);
                  return;
                }
                const spans = item.querySelectorAll('span');
                for (const span of spans) {
                  if (span.children.length > 0) continue;
                  const text = span.innerText.trim();
                  if (text.includes('·')) {
                    const name = text.split('·')[0].trim();
                    if (name && !companies.includes(name)) companies.push(name);
                    break;
                  }
                }
              } catch (_) { /* Eintrag überspringen */ }
            });
          }
        }
      } catch (_) { /* Experience-Section nicht verfügbar */ }
    }

    return companies;
  }

  function extractProfileData() {
    const name = extractName();
    const headline = extractHeadline();
    const { jobTitle, company } = parseHeadline(headline);
    const experienceCompanies = extractExperienceCompanies();

    if (company && !experienceCompanies.includes(company)) {
      experienceCompanies.unshift(company);
    }

    const result = {
      name,
      headline,
      jobTitle,
      company,
      location: extractLocation(),
      profileImageUrl: extractProfileImage(),
      linkedinUrl: extractLinkedInUrl(),
      experienceCompanies,
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
