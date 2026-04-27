// src/api.js — All API calls to Render backend
// Bug fix: sendReply now calls /api/reply/:id (no signature required)
// instead of /webhooks/email/reply (requires Resend HMAC — UI can't produce it)

const SERVER = import.meta.env.VITE_API_URL || 'https://conversion-engine10.onrender.com'

async function req(path, opts = {}) {
  const res = await fetch(`${SERVER}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal || AbortSignal.timeout(20000),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json()
}

export const api = {
  health:    ()             => req('/health'),
  companies: (search = '', limit = 100) =>
    req(`/api/companies?search=${encodeURIComponent(search)}&limit=${limit}`),
  prospects: ()             => req('/api/prospects'),
  prospect:  (id)           => req(`/api/prospect/${id}`),
  conversation: (id)        => req(`/api/conversation/${id}`),

  triggerProspect: (data)   => req('/outreach/prospect', { method: 'POST', body: data }),

  // Fixed: was /webhooks/email/reply which required a valid Resend HMAC signature.
  // The UI can never produce that, so it always returned 401.
  // Now calls /api/reply/:id which is the direct simulation endpoint — no signature needed.
  sendReply: (prospectId, text, channel = 'email') =>
    req(`/api/reply/${prospectId}`, {
      method: 'POST',
      body: { text, channel },
    }),

  smsInbound: (phone, text) =>
    fetch(`${SERVER}/webhooks/sms/inbound`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `from=${encodeURIComponent(phone)}&to=21271&text=${encodeURIComponent(text)}&date=${new Date().toISOString()}`,
    }).then(r => r.json()),
}