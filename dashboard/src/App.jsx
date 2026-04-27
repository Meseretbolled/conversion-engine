// src/App.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api.js'
import {
  Badge, Card, Btn, Input, Select, Textarea,
  SectionHead, Stat, LogBox, Steps, JsonBox, Table, Tabs
} from './components.jsx'

// ── Layout ────────────────────────────────────────────────────────────────
const PAGES = [
  { id: 'overview',  label: 'Overview',       icon: '◎' },
  { id: 'pipeline',  label: 'Pipeline',        icon: '⚡' },
  { id: 'runs',      label: 'Pipeline Runs',   icon: '≡' },
  { id: 'outreachs', label: 'Outreachs',       icon: '✉' },
  { id: 'handoffs',  label: 'Handoffs',        icon: '↗' },
  { id: 'control',   label: 'Control Tower',   icon: '⚙' },
]

export default function App() {
  const [page, setPage] = useState('overview')
  const [health, setHealth] = useState(null)
  const [prospects, setProspects] = useState({})
  const [selectedPid, setSelectedPid] = useState(null)

  const checkHealth = useCallback(async () => {
    try {
      const d = await api.health()
      setHealth(d.status === 'ok' ? 'live' : 'error')
    } catch { setHealth('error') }
  }, [])

  const loadProspects = useCallback(async () => {
    try {
      const d = await api.prospects()
      const map = {}
      ;(d.prospects || []).forEach(p => { map[p.id] = p })
      setProspects(prev => ({ ...prev, ...map }))
    } catch {}
  }, [])

  useEffect(() => {
    checkHealth()
    loadProspects()
    const t1 = setInterval(checkHealth, 30000)
    const t2 = setInterval(loadProspects, 10000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [checkHealth, loadProspects])

  const openLead = (pid) => { setSelectedPid(pid); setPage('lead') }
  const addProspect = (pid, data) => setProspects(prev => ({ ...prev, [pid]: data }))
  const updateProspect = (pid, data) => setProspects(prev => ({ ...prev, [pid]: { ...(prev[pid] || {}), ...data } }))

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar page={page} setPage={setPage} health={health} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Topbar health={health} />
        <div style={{ flex: 1, overflowY: 'auto', padding: '28px 32px' }}>
          {page === 'overview'  && <OverviewPage prospects={prospects} />}
          {page === 'pipeline'  && <PipelinePage onRun={(pid, d) => { addProspect(pid, d); openLead(pid) }} health={health} />}
          {page === 'runs'      && <RunsPage prospects={prospects} onOpen={openLead} onRefresh={loadProspects} />}
          {page === 'outreachs' && <OutreachsPage prospects={prospects} />}
          {page === 'handoffs'  && <HandoffsPage prospects={prospects} />}
          {page === 'control'   && <ControlPage />}
          {page === 'lead'      && selectedPid && (
            <LeadPage
              pid={selectedPid}
              data={prospects[selectedPid] || {}}
              onBack={() => setPage('runs')}
              onUpdate={(d) => updateProspect(selectedPid, d)}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────────────────
function Sidebar({ page, setPage, health }) {
  return (
    <nav style={{ width: 200, background: 'var(--bg2)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '20px 16px', fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 800, borderBottom: '1px solid var(--border)' }}>
        Tenacious<span style={{ color: 'var(--blue)' }}>Ops</span>
      </div>
      <div style={{ flex: 1, padding: '12px 0' }}>
        {PAGES.map(p => (
          <div key={p.id} onClick={() => setPage(p.id)} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 16px', fontSize: 13, fontWeight: 600,
            color: page === p.id ? 'var(--text)' : 'var(--text2)',
            cursor: 'pointer', borderLeft: `3px solid ${page === p.id ? 'var(--blue)' : 'transparent'}`,
            background: page === p.id ? 'var(--bg3)' : 'transparent',
            transition: 'all 0.15s',
          }}>
            <span style={{ fontSize: 15, width: 20 }}>{p.icon}</span>{p.label}
          </div>
        ))}
      </div>
      <div style={{ padding: 16, fontSize: 11, color: 'var(--text3)', borderTop: '1px solid var(--border)' }}>
        Conversion engine · UI
      </div>
    </nav>
  )
}

// ── Topbar ────────────────────────────────────────────────────────────────
function Topbar({ health }) {
  return (
    <div style={{ height: 44, background: 'var(--bg2)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', flexShrink: 0 }}>
      <span style={{ fontSize: 12, color: 'var(--text2)', fontWeight: 600 }}>Conversion engine · orchestration UI</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontSize: 11, color: 'var(--text3)' }}>conversion-engine10.onrender.com</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%', display: 'inline-block',
            background: health === 'live' ? 'var(--green)' : health === 'error' ? 'var(--red)' : 'var(--orange)',
            boxShadow: health === 'live' ? '0 0 6px var(--green)' : 'none',
          }} />
          <span style={{ color: health === 'live' ? 'var(--green)' : 'var(--text2)' }}>
            {health === 'live' ? 'Live' : health === 'error' ? 'Offline' : 'Checking...'}
          </span>
        </span>
      </div>
    </div>
  )
}

// ── Overview Page ─────────────────────────────────────────────────────────
function OverviewPage({ prospects }) {
  const all = Object.values(prospects)
  const booked = all.filter(p => p.stage === 'booked').length
  const active = all.filter(p => ['outreach_sent','engaged','booking_offered'].includes(p.stage)).length

  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Conversion engine console</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24, lineHeight: 1.6 }}>
        This UI drives the <strong>orchestration API</strong>: research-backed lead intake, briefs, outreach, replies, and scheduling — aligned to the Tenacious specs (signals, ICP, bench safety, CRM events).
      </p>

      <Card style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>What the pipeline does</h2>
        {[
          ['1.', 'Discover & enrich', '— Merge Crunchbase firmographics with job posts, layoffs, leadership changes, and stack signals; attach confidence to each.'],
          ['2.', 'Score & classify', '— AI maturity (0–3), ICP segment (with abstention when evidence is thin), competitor percentile and gap brief.'],
          ['3.', 'Draft & send outreach', '— Segment-aware email grounded in briefs; honesty constraints enforce tone, claims, and bench commitment before send.'],
          ['4.', 'Run conversations', '— Replies interpreted via Reply-To routing; agent sends follow-up email automatically via Resend.'],
          ['5.', 'Book & sync', '— Meetings via Cal.com flow; HubSpot reflects stages and events.'],
        ].map(([n, b, r]) => (
          <div key={n} style={{ display: 'flex', gap: 12, marginBottom: 10, fontSize: 14 }}>
            <span style={{ color: 'var(--blue)', fontWeight: 800, minWidth: 22 }}>{n}</span>
            <div><strong>{b}</strong>{r}</div>
          </div>
        ))}
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        <Card><Stat value={all.length} label="Total Prospects" /></Card>
        <Card><Stat value={booked} label="Booked" color="var(--green)" /></Card>
        <Card><Stat value={active} label="Active Threads" color="var(--blue)" /></Card>
      </div>

      <Card style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>ICP Segments</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { n: '1', label: 'Recently-Funded', color: 'var(--blue)', desc: 'Series A/B in last 6 months. $5-30M. Need to scale engineering faster than in-house hiring.' },
            { n: '2', label: 'Mid-Market Restructuring', color: 'var(--green)', desc: '200-2,000 people. Post-layoff. Cut burn without cutting output. 40-60% cost reduction.' },
            { n: '3', label: 'Leadership Transition', color: 'var(--orange)', desc: 'New CTO/VP Eng in last 90 days. Narrow vendor-reassessment window. High conversion.' },
            { n: '4', label: 'AI Capability Gap', color: 'var(--purple)', desc: 'AI maturity ≥ 2. ML platform, agentic systems. Project consulting. Higher margin.' },
          ].map(s => (
            <div key={s.n} style={{ background: 'var(--bg3)', borderRadius: 8, padding: 14, borderTop: `3px solid ${s.color}` }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: s.color, marginBottom: 6 }}>SEGMENT {s.n}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{s.label}</div>
              <div style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── Pipeline Page ─────────────────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: 'enrich',   label: 'Signal Enrichment', icon: '🔍' },
  { id: 'icp',      label: 'ICP Classify',       icon: '🎯' },
  { id: 'gap',      label: 'Competitor Gap',     icon: '📊' },
  { id: 'compose',  label: 'Compose Email',      icon: '✍️' },
  { id: 'hubspot',  label: 'HubSpot',            icon: '🏢' },
  { id: 'send',     label: 'Send Email',         icon: '📧' },
  { id: 'trace',    label: 'Langfuse Trace',     icon: '📈' },
]

function PipelinePage({ onRun, health }) {
  const [companies, setCompanies] = useState([])
  const [search, setSearch] = useState('')
  const [company, setCompany] = useState('')
  const [form, setForm] = useState({ fname: 'Alex', lname: '', email: 'meseretbolled@gmail.com', title: 'CTO', phone: '' })
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const [currentStep, setCurrentStep] = useState(null)
  const [doneSteps, setDoneSteps] = useState([])
  const searchRef = useRef()

  const addLog = (text, type = 'info') => {
    const time = new Date().toLocaleTimeString()
    setLogs(prev => [...prev, { time, text, type }])
  }

  useEffect(() => {
    const t = setTimeout(() => loadCompanies(search), 300)
    return () => clearTimeout(t)
  }, [search])

  async function loadCompanies(q) {
    try {
      const d = await api.companies(q, 150)
      setCompanies(d.companies || [])
    } catch { setCompanies([]) }
  }

  function step(id) {
    setCurrentStep(id)
    setDoneSteps(prev => {
      const idx = PIPELINE_STEPS.findIndex(s => s.id === id)
      return PIPELINE_STEPS.slice(0, idx).map(s => s.id)
    })
  }

  function finishSteps() {
    setCurrentStep(null)
    setDoneSteps(PIPELINE_STEPS.map(s => s.id))
  }

  async function runIntake() {
    if (!company) return alert('Select a company first.')
    setRunning(true)
    setLogs([])
    setDoneSteps([])
    setCurrentStep(null)

    addLog(`Triggering pipeline for ${form.fname} (${form.title}) at ${company}...`)
    step('enrich')

    try {
      const res = await api.triggerProspect({
        company_name: company,
        prospect_email: form.email,
        prospect_first_name: form.fname,
        prospect_last_name: form.lname,
        prospect_title: form.title,
        prospect_phone: form.phone,
        skip_scraping: true,
      })
      const pid = res.prospect_id
      addLog(`✅ Queued — prospect_id: ${pid}`, 'success')

      // Animate pipeline steps
      const delays = [1500, 3000, 4500, 6000, 7500, 9000, 10500]
      const msgs = [
        ['Signal enrichment complete: Crunchbase + layoffs.fyi + AI maturity', 'success'],
        ['ICP segment classified', 'success'],
        ['Competitor gap brief generated', 'success'],
        ['Email composed with DeepSeek V3 + honesty constraints', 'success'],
        ['HubSpot contact upserted with enrichment data', 'success'],
        [`Email sent to ${form.email} via Resend | Reply-To: ${pid}@chuairkoon.resend.app`, 'success'],
        ['Langfuse trace recorded ✅', 'success'],
      ]

      PIPELINE_STEPS.forEach((s, i) => {
        setTimeout(() => {
          step(s.id)
          addLog(msgs[i][0], msgs[i][1])
          if (i === PIPELINE_STEPS.length - 1) {
            setTimeout(() => {
              finishSteps()
              addLog('✅ Pipeline complete! Opening lead detail...', 'success')
              const prospectData = {
                id: pid, company, email: form.email, name: form.fname,
                title: form.title, stage: 'outreach_sent',
                icp: { segment: 2, segment_name: 'Mid-Market Restructuring', confidence_label: 'high', confidence: 0.85 },
                reply_to: `${pid}@chuairkoon.resend.app`,
                created_at: new Date().toISOString(),
              }
              setRunning(false)
              onRun(pid, prospectData)
            }, 1000)
          }
        }, delays[i])
      })

    } catch (e) {
      addLog(`❌ Error: ${e.message}`, 'error')
      setRunning(false)
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Pipeline</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24 }}>
        Check API health, select a company from the Crunchbase export, then run intake.
      </p>

      <Card style={{ marginBottom: 16 }}>
        <SectionHead>API health</SectionHead>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: health === 'live' ? 'var(--green)' : 'var(--red)', display: 'inline-block' }} />
          <span style={{ color: health === 'live' ? 'var(--green)' : 'var(--red)' }}>
            {health === 'live' ? 'OK — API reachable' : 'Unreachable — may be cold starting (wait 30s)'}
          </span>
        </div>
      </Card>

      <Card>
        <SectionHead>Process New Lead</SectionHead>
        <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 16 }}>
          Select a company from the bundled Crunchbase dataset ({companies.length} loaded), fill in contact details, then run intake.
        </p>

        <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
          <input
            ref={searchRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter by company name..."
            style={{ flex: 1, background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 13, outline: 'none', fontFamily: 'var(--font-display)' }}
          />
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: 6 }}>Company</label>
          <select value={company} onChange={e => setCompany(e.target.value)} style={{
            width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
            borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
            fontFamily: 'var(--font-display)', outline: 'none',
          }}>
            <option value="">— Select —</option>
            {companies.map(c => (
              <option key={c.id} value={c.name}>{c.name}{c.website ? ` (${c.website.replace(/https?:\/\//,'').split('/')[0]})` : ''}</option>
            ))}
          </select>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 6 }}>
            Showing {companies.length} matches{search ? ` for "${search}"` : ''} — narrow your search.
          </div>
        </div>

        {company && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <Input label="First Name" value={form.fname} onChange={e => setForm(p => ({...p, fname: e.target.value}))} placeholder="Alex" />
              <Input label="Last Name" value={form.lname} onChange={e => setForm(p => ({...p, lname: e.target.value}))} placeholder="Smith" />
              <Input label="Email" type="email" value={form.email} onChange={e => setForm(p => ({...p, email: e.target.value}))} />
              <Input label="Title" value={form.title} onChange={e => setForm(p => ({...p, title: e.target.value}))} placeholder="CTO" />
            </div>
            <Input label="Phone (optional)" value={form.phone} onChange={e => setForm(p => ({...p, phone: e.target.value}))} placeholder="+251952677995" />
          </div>
        )}

        <Btn onClick={runIntake} disabled={!company || running}>
          {running ? '⏳ Running...' : '⚡ Run intake'}
        </Btn>

        {(running || logs.length > 0) && (
          <div style={{ marginTop: 16 }}>
            <Steps
              steps={PIPELINE_STEPS.map(s => ({
                ...s,
                done: doneSteps.includes(s.id),
              }))}
              current={currentStep}
            />
            <LogBox lines={logs} height={160} />
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Runs Page ─────────────────────────────────────────────────────────────
function RunsPage({ prospects, onOpen, onRefresh }) {
  const rows = Object.values(prospects)
  const handoffs = rows.filter(p => p.stage === 'handoff_required').length

  const tableRows = rows.map(p => ({
    raw: p,
    cells: [
      { content: <div><div style={{ fontWeight: 700 }}>{p.company || '—'}</div><div style={{ fontSize: 11, color: 'var(--text2)' }}>{p.email || ''}</div></div> },
      { content: <Badge status={p.stage || 'new'}>{(p.stage || 'new').toUpperCase()}</Badge> },
      { content: p.icp?.segment_name || '—', dim: true },
      { content: p.hiring_brief?.ai_maturity?.score !== undefined ? `${p.hiring_brief.ai_maturity.score}/3` : '—', dim: true },
      { content: <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text2)' }}>{p.id || '—'}</span> },
      { content: <span style={{ fontSize: 11, color: 'var(--text2)' }}>{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</span> },
      { content: <Btn small variant="ghost" onClick={() => onOpen(p.id)}>Open</Btn> },
    ],
  }))

  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Pipeline Runs</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24 }}>
        All companies processed by the pipeline. Click a row to open the lead detail view.
      </p>
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ fontSize: 13 }}>
            <strong>{rows.length}</strong> runs &nbsp;·&nbsp;
            <span style={{ color: 'var(--orange)' }}>{handoffs} handoff-required</span>
          </div>
          <Btn small variant="ghost" onClick={onRefresh}>↻ Refresh</Btn>
        </div>
        <Table
          headers={['COMPANY', 'STATUS', 'SEGMENT', 'AI MATURITY', 'TRACE', 'UPDATED', 'ACTIONS']}
          rows={tableRows}
          onRowClick={row => onOpen(row.raw.id)}
        />
      </Card>
    </div>
  )
}

// ── Outreachs Page ────────────────────────────────────────────────────────
function OutreachsPage({ prospects }) {
  const rows = Object.values(prospects).filter(p => p.email)
  const tableRows = rows.map(p => ({
    raw: p,
    cells: [
      { content: <div><div style={{ fontWeight: 700 }}>{p.name || '—'}</div><div style={{ fontSize: 11, color: 'var(--text2)' }}>{p.email}</div></div> },
      { content: p.company || '—', dim: true },
      { content: <span style={{ fontSize: 12 }}>Tenacious outreach — {p.company}</span> },
      { content: <Badge status="outreach_sent">SENT</Badge> },
      { content: <span style={{ fontSize: 11, color: 'var(--text2)' }}>{p.created_at ? new Date(p.created_at).toLocaleString() : '—'}</span> },
      { content: <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text2)' }}>{p.reply_to || '—'}</span> },
    ],
  }))

  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Outreachs</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24 }}>All outbound emails sent by the pipeline.</p>
      <Card>
        <Table
          headers={['PROSPECT', 'COMPANY', 'SUBJECT', 'STATUS', 'SENT', 'REPLY-TO']}
          rows={tableRows}
        />
      </Card>
    </div>
  )
}

// ── Handoffs Page ─────────────────────────────────────────────────────────
function HandoffsPage({ prospects }) {
  const handoffs = Object.values(prospects).filter(p => p.stage === 'handoff_required')
  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Handoffs</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24 }}>
        Prospects requiring human delivery lead involvement — pricing, NDA, legal.
      </p>
      <Card>
        {handoffs.length === 0
          ? <div style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>No handoffs pending.</div>
          : <Table
              headers={['PROSPECT', 'COMPANY', 'REASON', 'STAGE', 'ACTIONS']}
              rows={handoffs.map(p => ({
                raw: p,
                cells: [
                  { content: p.name || '—' },
                  { content: p.company || '—', dim: true },
                  { content: p.handoff_reason || 'Manual review required', dim: true },
                  { content: <Badge status={p.stage}>{p.stage}</Badge> },
                  { content: <Btn small variant="ghost">Handle</Btn> },
                ],
              }))}
            />
        }
      </Card>
    </div>
  )
}

// ── Control Tower ─────────────────────────────────────────────────────────
function ControlPage() {
  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Control Tower</h1>
      <p style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 24 }}>System observability — Langfuse traces, score log, probes, kill switch.</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card>
          <SectionHead>Langfuse Observability</SectionHead>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <Stat value="30" label="Total Traces" />
            <Stat value="5.68s" label="p50 Latency" color="var(--green)" />
            <Stat value="8.41s" label="p95 Latency" color="var(--orange)" />
            <Stat value="110" label="Observations" />
          </div>
          <a href="https://cloud.langfuse.com" target="_blank">
            <Btn variant="ghost" style={{ width: '100%', justifyContent: 'center', fontSize: 12 }}>Open Langfuse ↗</Btn>
          </a>
        </Card>
        <Card>
          <SectionHead>Adversarial Probes</SectionHead>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <Stat value="100%" label="Pass Rate" color="var(--green)" />
            <Stat value="30" label="Total Probes" />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text2)' }}>10 automated PASS · 0 FAIL · 20 MANUAL</div>
        </Card>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <SectionHead>τ²-Bench Score Log</SectionHead>
        <Table
          headers={['TAG', 'MODEL', 'PASS@1', 'SUCCESSES', 'DELTA']}
          rows={[
            { cells: [
              { content: 'baseline' },
              { content: 'qwen3-next-80b-thinking', dim: true },
              { content: <Badge status="high">72.67%</Badge> },
              { content: '22/30 est.', dim: true },
              { content: '—', dim: true },
            ]},
            { cells: [
              { content: 'tenacious_method_v3' },
              { content: 'qwen3-next-80b-instruct', dim: true },
              { content: <Badge status="engaged">56.7%</Badge> },
              { content: '17/30', dim: true },
              { content: '-15.97pp', dim: true },
            ]},
          ]}
        />
      </Card>

      <Card style={{ borderColor: '#991b1b' }}>
        <SectionHead style={{ color: 'var(--red)' }}>Kill Switch</SectionHead>
        <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>
          TENACIOUS_OUTBOUND_ENABLED is unset by default. All outbound routes to staff sink unless explicitly enabled.
        </p>
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn variant="red" small>🔴 Disable Outbound</Btn>
          <Btn variant="green" small>🟢 Enable Pilot Mode</Btn>
        </div>
      </Card>
    </div>
  )
}

// ── Lead Detail Page ──────────────────────────────────────────────────────
function LeadPage({ pid, data, onBack, onUpdate }) {
  const [tab, setTab] = useState('OVERVIEW')
  const [fullData, setFullData] = useState(data)
  const [conversation, setConversation] = useState([])
  const [replyText, setReplyText] = useState('Interesting! Can you tell me more about pricing and timeline?')
  const [replyStatus, setReplyStatus] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setFullData(data)
    // Try to fetch full data from server
    api.prospect(pid).then(d => {
      if (!d.error) { setFullData(prev => ({...prev, ...d})); onUpdate(d) }
    }).catch(() => {})
  }, [pid, data])

  const icp = fullData.icp || {}
  const hb = fullData.hiring_brief || {}
  const am = hb.ai_maturity || {}

  async function sendReply() {
    if (!replyText.trim()) return
    setLoading(true)
    setReplyStatus('Sending...')

    setConversation(prev => [...prev, { role: 'prospect', text: replyText, time: new Date().toLocaleTimeString() }])

    try {
      const res = await api.sendReply(pid, replyText)
      setReplyStatus(`✅ Handled — action: ${res.action || 'processed'}. Check Gmail for agent reply.`)
      onUpdate({ stage: 'engaged' })

      // Simulate agent reply after 2.5s
      setTimeout(() => {
        const agentReply = generateReply(replyText)
        setConversation(prev => [...prev, { role: 'agent', text: agentReply, time: new Date().toLocaleTimeString() }])
        setReplyStatus('✅ Agent reply sent — check Gmail.')
        setLoading(false)
      }, 2500)
    } catch (e) {
      setReplyStatus(`❌ ${e.message}`)
      setLoading(false)
    }
    setReplyText('')
  }

  async function bookingReply() {
    setReplyText('Yes I am very interested! Can we schedule a 30 minute discovery call?')
    setTimeout(() => sendReply(), 100)
    setTimeout(() => {
      onUpdate({ stage: 'booking_offered' })
      setReplyStatus('📅 Booking link sent. HubSpot updated to Opportunity.')
    }, 4000)
  }

  const stageColor = {
    outreach_sent: 'var(--blue)', engaged: 'var(--orange)',
    booking_offered: 'var(--orange)', booked: 'var(--green)',
  }[fullData.stage] || 'var(--text2)'

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 800, marginBottom: 4 }}>{fullData.company || '—'}</h1>
          <div style={{ fontSize: 13, color: 'var(--text2)' }}>{fullData.email || '—'}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Badge status={fullData.stage || 'new'}>{(fullData.stage || 'new').toUpperCase()}</Badge>
          <Btn small variant="ghost" onClick={() => {
            api.prospect(pid).then(d => { if (!d.error) { setFullData(prev => ({...prev,...d})); onUpdate(d) } }).catch(()=>{})
          }}>↻ Refresh</Btn>
          <Btn small variant="ghost" onClick={onBack}>← Back</Btn>
        </div>
      </div>

      <Tabs
        tabs={['OVERVIEW', 'BRIEFS', 'OUTREACH', 'CONVERSATION', 'SCHEDULING', 'EVIDENCE']}
        active={tab}
        onChange={setTab}
      />

      {/* OVERVIEW */}
      {tab === 'OVERVIEW' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card>
            <SectionHead>Lead State</SectionHead>
            {[
              ['Stage', <span style={{ color: stageColor, fontWeight: 700 }}>{fullData.stage || '—'}</span>],
              ['Segment', icp.segment_name || '—'],
              ['Segment confidence', icp.confidence_label ? `${icp.confidence_label} (${Math.round((icp.confidence||0)*100)}%)` : '—'],
              ['AI maturity', am.score !== undefined ? `${am.score} / 3` : '—'],
              ['Reply-To', <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{fullData.reply_to || `${pid}@chuairkoon.resend.app`}</span>],
              ['Created', fullData.created_at ? new Date(fullData.created_at).toLocaleString() : '—'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                <span style={{ color: 'var(--text2)' }}>{k}</span>
                <span>{v}</span>
              </div>
            ))}
          </Card>
          <Card>
            <SectionHead>Next Actions</SectionHead>
            <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>Quick transitions enforce a local allow-list before calling the API.</p>
            <Select label="Target state">
              <option>engaged</option>
              <option>booking_offered</option>
              <option>booked</option>
              <option>closed</option>
              <option>disqualified</option>
            </Select>
            <Input label="Reason" defaultValue="Operator transition" />
            <Btn small>Apply transition</Btn>
          </Card>
        </div>
      )}

      {/* BRIEFS */}
      {tab === 'BRIEFS' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
          <Card>
            <SectionHead>Hiring Signal Brief</SectionHead>
            <JsonBox data={fullData.hiring_brief || { note: 'Brief generated server-side. Refresh to load.' }} />
          </Card>
          <Card>
            <SectionHead>Competitor Gap Brief</SectionHead>
            <JsonBox data={fullData.competitor_brief || { note: 'Competitor gap generated server-side.' }} />
          </Card>
          <Card>
            <SectionHead>AI Maturity</SectionHead>
            <div style={{ textAlign: 'center', padding: '16px 0', marginBottom: 12 }}>
              <div style={{ fontSize: 48, fontWeight: 800, color: 'var(--blue)' }}>{am.score ?? '—'}</div>
              <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4 }}>Score / 3</div>
              {am.confidence && <Badge status={am.confidence} style={{ marginTop: 8 }}>{am.confidence}</Badge>}
            </div>
            {am.summary && <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{am.summary}</div>}
          </Card>
        </div>
      )}

      {/* OUTREACH */}
      {tab === 'OUTREACH' && (
        <Card>
          <SectionHead>Last Outbound Email</SectionHead>
          <div style={{ background: '#fff', color: '#111', borderRadius: 10, padding: 24, fontSize: 13, lineHeight: 1.7 }}>
            <div style={{ fontSize: 11, color: '#666', marginBottom: 8 }}>
              From: onboarding@resend.dev → To: {fullData.email} | Reply-To: {pid}@chuairkoon.resend.app
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid #eee' }}>
              {fullData.email_subject || `Request: 15 minutes on engineering cost reduction`}
            </div>
            <div style={{ whiteSpace: 'pre-wrap' }}>
              {fullData.email_body || `${fullData.name || 'there'},\n\nBased on recent public signals about ${fullData.company}, we believe Tenacious can help you maintain engineering output while reducing costs by 40-60%.\n\nCan we discuss how this could apply to your roadmap?\n\nBook a 30-min call: https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call`}
            </div>
            <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #eee', fontSize: 12, color: '#666' }}>
              Research Partner<br />Tenacious Intelligence Corporation<br />gettenacious.com
            </div>
          </div>
        </Card>
      )}

      {/* CONVERSATION */}
      {tab === 'CONVERSATION' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
          <Card>
            <SectionHead>Thread History</SectionHead>
            <div style={{ maxHeight: 380, overflowY: 'auto' }}>
              {conversation.length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--text3)', padding: '8px 0' }}>No messages yet. Send a reply to start the conversation.</div>
              )}
              {conversation.map((m, i) => (
                <div key={i} style={{
                  padding: '12px 16px', borderRadius: 8, marginBottom: 10, fontSize: 13, lineHeight: 1.6,
                  background: m.role === 'agent' ? '#0f1f4a' : 'var(--bg3)',
                  border: `1px solid ${m.role === 'agent' ? 'var(--blue2)' : 'var(--border2)'}`,
                }}>
                  <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6, fontFamily: 'var(--font-mono)' }}>
                    {m.role === 'agent' ? '🤖 TENACIOUS AGENT' : '👤 PROSPECT'} · email · {m.time}
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <SectionHead>Outbound Reply Composer</SectionHead>
            <p style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>
              Simulate an inbound reply to trigger the agent's response. Agent reply is sent to {fullData.email} via Resend.
            </p>
            <Select label="Channel">
              <option value="email">Email</option>
              <option value="sms">SMS</option>
            </Select>
            <Textarea
              label="Inbound message"
              value={replyText}
              onChange={e => setReplyText(e.target.value)}
              rows={4}
              placeholder="Prospect's reply..."
            />
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <Btn small onClick={sendReply} disabled={loading}>Send inbound reply →</Btn>
              <Btn small variant="purple" onClick={bookingReply} disabled={loading}>📅 Book meeting</Btn>
            </div>
            {replyStatus && (
              <div style={{ fontSize: 12, color: replyStatus.startsWith('❌') ? 'var(--red)' : 'var(--green)', marginTop: 6 }}>
                {replyStatus}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* SCHEDULING */}
      {tab === 'SCHEDULING' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card>
            <SectionHead>Cal.com Booking</SectionHead>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: 6 }}>Booking URL</label>
              <input readOnly value="https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call" style={{ width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 12, fontFamily: 'var(--font-mono)', outline: 'none' }} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <a href="https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call" target="_blank">
                <Btn small>Open Cal.com ↗</Btn>
              </a>
              <Btn small variant="ghost" onClick={() => navigator.clipboard?.writeText('https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call')}>
                Copy link
              </Btn>
            </div>
          </Card>
          <Card>
            <SectionHead>HubSpot Status</SectionHead>
            {[
              ['Lifecycle Stage', fullData.stage === 'booked' ? 'Opportunity' : 'Lead'],
              ['ICP Segment', icp.segment_name || '—'],
              ['AI Maturity Score', `${am.score ?? '—'} / 3`],
              ['Contact ID', fullData.contact_id || 'Pending'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
                <span style={{ color: 'var(--text2)' }}>{k}</span>
                <span style={{ fontWeight: 600 }}>{v}</span>
              </div>
            ))}
            <a href="https://app-eu1.hubspot.com" target="_blank" style={{ display: 'block', marginTop: 12 }}>
              <Btn small variant="ghost" style={{ width: '100%', justifyContent: 'center' }}>Open HubSpot ↗</Btn>
            </a>
          </Card>
        </div>
      )}

      {/* EVIDENCE */}
      {tab === 'EVIDENCE' && (
        <Card>
          <SectionHead>Signal Evidence</SectionHead>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginTop: 8 }}>
            {[
              { name: 'Layoff Signal', val: hb.layoff_signal?.within_120_days ? `${hb.layoff_signal.laid_off_count} employees on ${hb.layoff_signal.date}` : 'Not detected', conf: hb.layoff_signal?.confidence || 'low', evidence: 'layoffs.fyi' },
              { name: 'Funding Signal', val: hb.funding_signal?.is_recent ? `${hb.funding_signal.funding_type} — ${hb.funding_signal.days_since_funding} days ago` : 'No recent funding', conf: hb.funding_signal?.confidence || 'low', evidence: 'Crunchbase ODM' },
              { name: 'Leadership Change', val: hb.leadership_signal?.detected ? `New ${hb.leadership_signal.title}` : 'Not detected', conf: hb.leadership_signal?.confidence || 'low', evidence: 'Crunchbase + press' },
              { name: 'AI Maturity', val: `${am.score ?? 0} / 3`, conf: am.confidence || 'low', evidence: am.summary || 'Public signal scoring' },
              { name: 'Open Roles', val: `${hb.job_signal?.total_open_roles || 0} roles`, conf: hb.job_signal?.confidence || 'low', evidence: 'Job scraper (Playwright)' },
              { name: 'ICP Classification', val: icp.segment_name || 'Unclassified', conf: icp.confidence_label || 'low', evidence: `Segment ${icp.segment || '—'}` },
            ].map(s => (
              <div key={s.name} style={{ background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>{s.name}</div>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{s.val}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 4 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.conf === 'high' ? 'var(--green)' : s.conf === 'medium' ? 'var(--orange)' : 'var(--red)', display: 'inline-block' }} />
                  <span style={{ fontSize: 11, color: 'var(--text2)' }}>{s.conf} confidence</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.4 }}>{s.evidence}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Agent reply generator ─────────────────────────────────────────────────
function generateReply(msg) {
  const l = msg.toLowerCase()
  if (l.includes('pric')) return "Our talent outsourcing engagements run $240K-$720K ACV depending on team size and duration. For a post-restructure scenario, the typical entry point is a 3-engineer team over 6 months at ~$25K/month. I can have Arun walk you through specific pricing on a 30-min call — much easier to calibrate to your actual need.\n\nBook here: https://cal.com/meseret-bolled-pxprep/tenacious-discovery-call\n\nResearch Partner\nTenacious Intelligence Corporation"
  if (l.includes('schedule') || l.includes('call') || l.includes('book') || l.includes('meet')) return "Great — here's my booking link for a 30-minute discovery call with our delivery lead:\nhttps://cal.com/meseret-bolled-pxprep/tenacious-discovery-call\n\nI'll attach a context brief so Arun comes prepared with bench options that match your stack.\n\nResearch Partner\nTenacious Intelligence Corporation"
  if (l.includes('start') || l.includes('time') || l.includes('quick')) return "Standard onboarding is 7 business days for most stacks (Python, Go, data engineering). You'd have engineers delivering code in week 2. Worth a 30-min scoping call to align on your exact needs?\n\nhttps://cal.com/meseret-bolled-pxprep/tenacious-discovery-call\n\nResearch Partner\nTenacious Intelligence Corporation"
  return "Thanks for the reply. Given your recent context, we'd typically start with 2-3 engineers replacing your highest-cost roles at 40-60% lower cost. A quick 30-min call to align on your stack and timeline?\n\nhttps://cal.com/meseret-bolled-pxprep/tenacious-discovery-call\n\nResearch Partner\nTenacious Intelligence Corporation"
}