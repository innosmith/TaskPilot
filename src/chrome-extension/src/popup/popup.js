/**
 * TaskPilot LinkedIn Sync – Popup Logic
 * Steuert die drei Zustände: Neu / Existiert / Update.
 *
 * Alle strukturierten Profildaten (Name, Headline, Rolle, Firma, Ort)
 * kommen ausschliesslich vom LLM-Backend. Das Content Script liefert
 * nur linkedinUrl, profileImageUrl und den rohen Seitentext.
 */

let profileData = null;
let lookupResult = null;

const states = [
  'state-not-linkedin', 'state-loading', 'state-new',
  'state-exists', 'state-update', 'state-multiple',
  'state-success', 'state-error',
];

function showState(stateId) {
  states.forEach(id => {
    document.getElementById(id).classList.toggle('hidden', id !== stateId);
  });
}

function sendToBackground(action, payload) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action, payload }, resolve);
  });
}

async function extractProfileFromTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url || !tab.url.includes('linkedin.com/in/')) {
    return null;
  }

  const rawData = await new Promise((resolve) => {
    chrome.tabs.sendMessage(tab.id, { action: 'extractProfile' }, (response) => {
      if (chrome.runtime.lastError || !response || !response.success) {
        resolve(null);
      } else {
        resolve(response.data);
      }
    });
  });

  if (!rawData || !rawData.pageText) return null;

  const result = {
    linkedinUrl: rawData.linkedinUrl || '',
    profileImageUrl: rawData.profileImageUrl || '',
    name: '',
    headline: '',
    jobTitle: '',
    company: '',
    location: '',
    experienceCompanies: [],
    _debug: { source: 'LLM' },
  };

  try {
    const llmResult = await sendToBackground('extractProfileLLM', {
      html: rawData.pageText,
    });

    if (llmResult && llmResult.data && !llmResult.error) {
      const llm = llmResult.data;
      result.name = llm.name || '';
      result.headline = llm.headline || '';
      result.jobTitle = llm.job_title || '';
      result.location = llm.location || '';
      result.experienceCompanies = llm.companies || [];
      result.company = (llm.companies && llm.companies.length > 0) ? llm.companies[0] : '';
      result._debug.llmSuccess = true;
    } else {
      result._debug.llmSuccess = false;
      result._debug.llmError = llmResult?.error || 'Unbekannter Fehler';
    }
  } catch (err) {
    result._debug.llmSuccess = false;
    result._debug.llmError = err.message;
  }

  return result;
}

function populateNewState(data) {
  const avatar = document.getElementById('new-avatar');
  if (data.profileImageUrl) {
    avatar.src = data.profileImageUrl;
    avatar.style.display = 'block';
  } else {
    avatar.style.display = 'none';
  }

  document.getElementById('new-name').value = data.name || '';
  document.getElementById('new-job-title').value = data.jobTitle || '';
  document.getElementById('new-location').value = data.location || '';

  const orgSelect = document.getElementById('new-org');
  orgSelect.innerHTML = '';
  const companies = data.experienceCompanies || [];
  if (data.company && !companies.includes(data.company)) {
    companies.unshift(data.company);
  }
  if (companies.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '— Keine Organisation —';
    orgSelect.appendChild(opt);
  }
  companies.forEach((company, idx) => {
    const opt = document.createElement('option');
    opt.value = company;
    opt.textContent = company;
    if (idx === 0) opt.selected = true;
    orgSelect.appendChild(opt);
  });
  const emptyOpt = document.createElement('option');
  emptyOpt.value = '';
  emptyOpt.textContent = '— Ohne Organisation —';
  orgSelect.appendChild(emptyOpt);
}

function populateExistsState(match) {
  const avatar = document.getElementById('exists-avatar');
  if (match.pic_url) {
    avatar.src = match.pic_url;
    avatar.style.display = 'block';
  } else {
    avatar.style.display = 'none';
  }
  document.getElementById('exists-name').textContent = match.name;
  document.getElementById('exists-org').textContent = match.org_name || '';
  document.getElementById('exists-link').href = match.pipedrive_url;
}

function populateUpdateState(match) {
  const avatar = document.getElementById('update-avatar');
  if (match.pic_url || (profileData && profileData.profileImageUrl)) {
    avatar.src = match.pic_url || profileData.profileImageUrl;
    avatar.style.display = 'block';
  } else {
    avatar.style.display = 'none';
  }
  document.getElementById('update-name').textContent = match.name;
  document.getElementById('update-org').textContent = match.org_name || '';
  document.getElementById('update-link').href = match.pipedrive_url;

  const diffList = document.getElementById('diff-list');
  diffList.innerHTML = '';
  match.changes.forEach((change) => {
    const item = document.createElement('div');
    item.className = 'diff-item';
    item.innerHTML = `
      <input type="checkbox" checked data-field="${change.field}">
      <span class="diff-label">${change.field_label}</span>
      ${change.old_value ? `<span class="diff-old">${change.old_value}</span>` : '<span class="diff-old">—</span>'}
      <span class="diff-arrow">→</span>
      <span class="diff-new">${change.new_value || '—'}</span>
    `;
    diffList.appendChild(item);
  });
}

function populateMultipleState(matches) {
  const list = document.getElementById('multiple-list');
  list.innerHTML = '';
  matches.forEach((match) => {
    const item = document.createElement('div');
    item.className = 'multiple-item';
    item.innerHTML = `
      <img class="avatar-small" src="${match.pic_url || ''}" alt=""
           style="${match.pic_url ? '' : 'display:none'}">
      <div class="multiple-item-info">
        <div class="multiple-item-name">${match.name}</div>
        <div class="multiple-item-org">${match.org_name || '—'}</div>
      </div>
    `;
    item.addEventListener('click', () => selectExistingMatch(match));
    list.appendChild(item);
  });
}

function selectExistingMatch(match) {
  if (match.changes && match.changes.length > 0) {
    populateUpdateState(match);
    lookupResult = { match_type: 'name', matches: [match] };
    showState('state-update');
  } else {
    populateExistsState(match);
    showState('state-exists');
  }
}

async function doLookup() {
  showState('state-loading');

  const result = await sendToBackground('linkedinLookup', {
    name: profileData.name,
    linkedin_url: profileData.linkedinUrl,
    org_name: profileData.company,
    job_title: profileData.jobTitle,
    profile_image_url: profileData.profileImageUrl,
  });

  if (result.error) {
    document.getElementById('error-text').textContent = result.error;
    showState('state-error');
    return;
  }

  lookupResult = result.data;
  const { match_type, matches } = lookupResult;

  if (match_type === 'none' || matches.length === 0) {
    populateNewState(profileData);
    showState('state-new');
  } else if (match_type === 'linkedin_url' && matches.length === 1) {
    const match = matches[0];
    if (match.changes && match.changes.length > 0) {
      populateUpdateState(match);
      showState('state-update');
    } else {
      populateExistsState(match);
      showState('state-exists');
    }
  } else if (matches.length === 1) {
    const match = matches[0];
    if (match.changes && match.changes.length > 0) {
      populateUpdateState(match);
      showState('state-update');
    } else {
      populateExistsState(match);
      showState('state-exists');
    }
  } else {
    populateMultipleState(matches);
    showState('state-multiple');
  }
}

async function doCreate() {
  const btn = document.getElementById('btn-create');
  btn.disabled = true;
  btn.textContent = 'Wird erstellt…';

  const result = await sendToBackground('linkedinSync', {
    action: 'create',
    name: document.getElementById('new-name').value,
    org_name: document.getElementById('new-org').value || null,
    job_title: document.getElementById('new-job-title').value || null,
    linkedin_url: profileData.linkedinUrl,
    profile_image_url: profileData.profileImageUrl || null,
  });

  if (result.error) {
    document.getElementById('error-text').textContent = result.error;
    showState('state-error');
    return;
  }

  document.getElementById('success-text').textContent = `${result.data.name} wurde erstellt`;
  document.getElementById('success-link').href = result.data.pipedrive_url;
  showState('state-success');
}

async function doUpdate() {
  const btn = document.getElementById('btn-update');
  btn.disabled = true;
  btn.textContent = 'Wird aktualisiert…';

  const checkboxes = document.querySelectorAll('#diff-list input[type="checkbox"]:checked');
  const updateFields = [...checkboxes].map(cb => cb.dataset.field);

  if (updateFields.length === 0) {
    btn.disabled = false;
    btn.textContent = 'Ausgewählte Felder aktualisieren';
    return;
  }

  const match = lookupResult.matches[0];

  const result = await sendToBackground('linkedinSync', {
    action: 'update',
    person_id: match.person_id,
    name: match.name,
    org_name: profileData.company || null,
    job_title: profileData.jobTitle || null,
    linkedin_url: profileData.linkedinUrl,
    profile_image_url: profileData.profileImageUrl || null,
    update_fields: updateFields,
  });

  if (result.error) {
    document.getElementById('error-text').textContent = result.error;
    showState('state-error');
    return;
  }

  document.getElementById('success-text').textContent =
    `${result.data.name} aktualisiert (${result.data.fields_updated.length} Felder)`;
  document.getElementById('success-link').href = result.data.pipedrive_url;
  showState('state-success');
}

function populateDebugPreview(data) {
  const preview = document.getElementById('debug-preview');
  const tbody = document.querySelector('#debug-table tbody');
  if (!preview || !tbody || !data) return;

  tbody.innerHTML = '';

  const fields = [
    { label: 'Name', value: data.name, source: 'LLM' },
    { label: 'Headline', value: data.headline, source: 'LLM' },
    { label: 'Akt. Rolle', value: data.jobTitle, source: 'LLM' },
    { label: 'Akt. Firma', value: data.company, source: 'LLM' },
    { label: 'Ort', value: data.location, source: 'LLM' },
    { label: 'Firmen', value: data.experienceCompanies?.join(', '), source: 'LLM' },
    { label: 'Bild', value: data.profileImageUrl ? 'vorhanden' : 'nicht gefunden', source: 'DOM (CDN)' },
    { label: 'URL', value: data.linkedinUrl, source: 'DOM (Browser)' },
  ];

  if (data._debug) {
    const d = data._debug;
    const parts = [`Quelle: ${d.source || '?'}`];
    if (d.llmSuccess !== undefined) parts.push(`LLM: ${d.llmSuccess ? 'OK' : 'Fehler'}`);
    if (d.llmError) parts.push(`Fehler: ${d.llmError}`);
    fields.push({ label: 'Diagnose', value: parts.join(' · ') });
  }

  for (const field of fields) {
    if (!field.value) continue;
    const tr = document.createElement('tr');
    const sourceTag = field.source ? ` <span class="debug-source">(${field.source})</span>` : '';
    tr.innerHTML = `<td>${field.label}</td><td>${field.value}${sourceTag}</td>`;
    tbody.appendChild(tr);
  }

  preview.classList.remove('hidden');
}

// Event Listeners
document.addEventListener('DOMContentLoaded', async () => {
  showState('state-loading');
  profileData = await extractProfileFromTab();
  if (!profileData) {
    showState('state-not-linkedin');
    return;
  }
  populateDebugPreview(profileData);
  await doLookup();
});

document.getElementById('btn-create').addEventListener('click', doCreate);
document.getElementById('btn-update').addEventListener('click', doUpdate);
document.getElementById('btn-retry').addEventListener('click', () => doLookup());

document.getElementById('btn-create-anyway').addEventListener('click', () => {
  populateNewState(profileData);
  showState('state-new');
});

document.getElementById('btn-settings').addEventListener('click', () => {
  chrome.tabs.create({ url: chrome.runtime.getURL('src/options/options.html') });
});
