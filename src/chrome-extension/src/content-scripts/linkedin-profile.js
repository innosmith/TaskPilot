/**
 * TaskPilot LinkedIn Sync – Content Script
 * Extrahiert Profildaten aus LinkedIn /in/*-Seiten.
 */

(() => {
  'use strict';

  function extractText(selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const text = el.innerText.trim();
        if (text) return text;
      }
    }
    return '';
  }

  function extractProfileImage() {
    const selectors = [
      'img.pv-top-card-profile-picture__image--show',
      'img.pv-top-card-profile-picture__image',
      '.pv-top-card__photo img',
      'img.profile-photo-edit__preview',
      'img.presence-entity__image',
    ];
    for (const sel of selectors) {
      const img = document.querySelector(sel);
      if (img && img.src && img.src.startsWith('http') && !img.src.includes('ghost')) {
        return img.src;
      }
    }
    const headerImg = document.querySelector('.pv-top-card img[src*="profile-displayphoto"]');
    if (headerImg) return headerImg.src;
    return '';
  }

  function extractName() {
    const h1 = document.querySelector('h1');
    return h1 ? h1.innerText.trim() : '';
  }

  function extractHeadline() {
    return extractText([
      '.text-body-medium.break-words',
      '.pv-top-card--list .text-body-medium',
      '[data-generated-suggestion-target] .text-body-medium',
    ]);
  }

  function extractLocation() {
    return extractText([
      '.pv-top-card--list .text-body-small.inline.t-black--light.break-words',
      '.pv-top-card--list-bullet .text-body-small',
      'span.text-body-small.inline.t-black--light.break-words',
    ]);
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

  function extractExperienceCompanies() {
    const companies = [];
    try {
      const experienceSection = document.querySelector('[id="experience"]');
      if (!experienceSection) return companies;
      const container = experienceSection.nextElementSibling?.nextElementSibling;
      if (!container) return companies;
      const entries = container.querySelector('ul')?.querySelectorAll(':scope > li');
      if (!entries) return companies;

      entries.forEach((entry) => {
        try {
          const topDiv = entry.querySelector('div');
          if (!topDiv) return;
          const dataContainer = topDiv.querySelectorAll(':scope > div')[1];
          if (!dataContainer) return;

          const rolesList = dataContainer.querySelector(':scope > div > ul');
          const roleItems = rolesList?.querySelectorAll(':scope > li');
          const isMultiRole = !!roleItems && [...roleItems].some(li => li.querySelector('.t-bold span'));

          if (isMultiRole) {
            const companyEl = dataContainer.querySelector('a div span');
            if (companyEl) {
              const name = companyEl.innerText.trim();
              if (name && !companies.includes(name)) companies.push(name);
            }
          } else {
            const companyAndType = dataContainer.querySelector('span.t-14.t-normal span');
            if (companyAndType) {
              const parts = companyAndType.innerText.trim().split('·').map(p => p.trim());
              const name = parts[0];
              if (name && !companies.includes(name)) companies.push(name);
            }
          }
        } catch (_) { /* entry parsing error – skip */ }
      });
    } catch (_) { /* experience section error – skip */ }
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

    return {
      name,
      headline,
      jobTitle,
      company,
      location: extractLocation(),
      profileImageUrl: extractProfileImage(),
      linkedinUrl: extractLinkedInUrl(),
      experienceCompanies,
    };
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
