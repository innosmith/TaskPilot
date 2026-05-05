/**
 * TaskPilot LinkedIn Sync – Background Service Worker
 * Alle API-Calls laufen hier (umgeht CORS-Einschränkungen).
 */

async function getConfig() {
  const result = await chrome.storage.sync.get([
    'backendUrl', 'apiToken', 'cfClientId', 'cfClientSecret',
  ]);
  return {
    backendUrl: (result.backendUrl || 'https://tp.innosmith.ai').replace(/\/+$/, ''),
    apiToken: result.apiToken || '',
    cfClientId: result.cfClientId || '',
    cfClientSecret: result.cfClientSecret || '',
  };
}

async function apiRequest(method, path, body) {
  const config = await getConfig();
  if (!config.apiToken) {
    return { error: 'API-Key nicht konfiguriert. Bitte in den Einstellungen hinterlegen.' };
  }

  const url = `${config.backendUrl}${path}`;
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${config.apiToken}`,
  };

  if (config.cfClientId && config.cfClientSecret) {
    headers['CF-Access-Client-Id'] = config.cfClientId;
    headers['CF-Access-Client-Secret'] = config.cfClientSecret;
  }

  const options = { method, headers };
  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      if (response.status === 302 || response.status === 403 || response.url.includes('cloudflareaccess')) {
        return { error: 'Cloudflare Access blockiert den Zugriff. Bitte CF-Access Client-ID und Secret in den Einstellungen hinterlegen.' };
      }
      return { error: `Unerwartete Antwort (${response.status}). Prüfe die Backend-URL.` };
    }

    const data = await response.json();
    if (!response.ok) {
      return { error: data.detail || `HTTP ${response.status}` };
    }
    return { data };
  } catch (err) {
    if (err.message === 'Failed to fetch') {
      return { error: 'Verbindung fehlgeschlagen. Prüfe Backend-URL und Cloudflare-Access-Einstellungen.' };
    }
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

  if (request.action === 'extractProfileLLM') {
    apiRequest('POST', '/api/linkedin/extract-profile', { html: request.payload.html })
      .then(sendResponse);
    return true;
  }

  if (request.action === 'testConnection') {
    apiRequest('GET', '/api/pipedrive/test-connection')
      .then(sendResponse);
    return true;
  }
});
