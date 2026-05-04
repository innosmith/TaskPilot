/**
 * TaskPilot LinkedIn Sync – Background Service Worker
 * Alle API-Calls laufen hier (umgeht CORS-Einschraenkungen).
 */

async function getConfig() {
  const result = await chrome.storage.sync.get(['backendUrl', 'apiToken']);
  return {
    backendUrl: (result.backendUrl || 'http://localhost:8000').replace(/\/+$/, ''),
    apiToken: result.apiToken || '',
  };
}

async function apiRequest(method, path, body) {
  const config = await getConfig();
  if (!config.apiToken) {
    return { error: 'API-Token nicht konfiguriert. Bitte in den Einstellungen hinterlegen.' };
  }

  const url = `${config.backendUrl}${path}`;
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiToken}`,
    },
  };
  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) {
      return { error: data.detail || `HTTP ${response.status}` };
    }
    return { data };
  } catch (err) {
    return { error: `Verbindungsfehler: ${err.message}` };
  }
}

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === 'linkedinLookup') {
    apiRequest('POST', '/api/pipedrive/linkedin-lookup', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'linkedinSync') {
    apiRequest('POST', '/api/pipedrive/linkedin-sync', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'testConnection') {
    apiRequest('GET', '/api/pipedrive/test-connection')
      .then(sendResponse);
    return true;
  }
});
