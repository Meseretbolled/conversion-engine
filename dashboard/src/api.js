// src/api.js — All API calls to Render backend

const SERVER = import.meta.env.VITE_API_URL || 'https://conversion-engine10.onrender.com'

async function req(path, opts = {}) {
  const res = await fetch(`${SERVER}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal || AbortSignal.timeout(15000),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  health:       ()           => req('/health'),
  companies:    (search='',limit=100) => req(`/api/companies?search=${encodeURIComponent(search)}&limit=${limit}`),
  prospects:    ()           => req('/api/prospects'),
  prospect:     (id)         => req(`/api/prospect/${id}`),

  triggerProspect: (data)    => req('/outreach/prospect', { method: 'POST', body: data }),

  sendReply: (prospectId, text, subject='Re: Tenacious outreach') =>
    req('/webhooks/email/reply', {
      method: 'POST',
      body: {
        type: 'email.received',
        data: {
          email_id: `sim_${Date.now()}`,
          from: 'prospect@company.com',
          to: [`${prospectId}@chuairkoon.resend.app`],
          subject,
          text,
          tags: [{ name: 'prospect_id', value: prospectId }],
        },
      },
    }),

  smsInbound: (phone, text) =>
    fetch(`${SERVER}/webhooks/sms/inbound`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `from=${encodeURIComponent(phone)}&to=21271&text=${encodeURIComponent(text)}&date=${new Date().toISOString()}`,
    }).then(r => r.json()),
}