// src/components.jsx — Shared UI primitives

import React from 'react'

// ── Badge ──────────────────────────────────────────────────────────────────
const BADGE_COLORS = {
  booked:          { bg: '#052e1c', color: '#0fd68a', border: '#065f46' },
  outreach_sent:   { bg: '#0f1f4a', color: '#4f8ef7', border: '#1a4fbf' },
  engaged:         { bg: '#3d1c02', color: '#f5a623', border: '#92400e' },
  booking_offered: { bg: '#3d1c02', color: '#f5a623', border: '#92400e' },
  disqualified:    { bg: '#3d0505', color: '#f05252', border: '#991b1b' },
  new:             { bg: '#1a2035', color: '#7a8499', border: '#253050' },
  briefs_ready:    { bg: '#1c1040', color: '#9f7aea', border: '#5b21b6' },
  high:            { bg: '#052e1c', color: '#0fd68a', border: '#065f46' },
  medium:          { bg: '#3d1c02', color: '#f5a623', border: '#92400e' },
  low:             { bg: '#3d0505', color: '#f05252', border: '#991b1b' },
}

export function Badge({ status, children }) {
  const s = (status || '').toLowerCase().replace(/ /g, '_')
  const c = BADGE_COLORS[s] || BADGE_COLORS.new
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      textTransform: 'uppercase', letterSpacing: '0.6px',
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    }}>
      {children || status}
    </span>
  )
}

// ── Card ───────────────────────────────────────────────────────────────────
export function Card({ children, style, onClick }) {
  return (
    <div onClick={onClick} style={{
      background: 'var(--bg2)', border: '1px solid var(--border)',
      borderRadius: 10, padding: 20, ...style,
      ...(onClick ? { cursor: 'pointer' } : {}),
    }}>
      {children}
    </div>
  )
}

// ── Btn ────────────────────────────────────────────────────────────────────
export function Btn({ children, onClick, variant = 'primary', small, disabled, style }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 7,
    padding: small ? '6px 12px' : '10px 18px',
    borderRadius: 7, fontSize: small ? 12 : 13, fontWeight: 700,
    border: 'none', transition: 'all 0.15s',
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? 'not-allowed' : 'pointer',
    ...style,
  }
  const variants = {
    primary: { background: 'var(--blue)', color: '#fff' },
    ghost:   { background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text2)' },
    green:   { background: 'var(--green)', color: '#000' },
    red:     { background: '#7f1d1d', color: '#fca5a5', border: '1px solid #991b1b' },
    purple:  { background: '#2e1065', color: '#c4b5fd', border: '1px solid #5b21b6' },
  }
  return (
    <button onClick={!disabled ? onClick : undefined} style={{ ...base, ...variants[variant] }}>
      {children}
    </button>
  )
}

// ── Input ─────────────────────────────────────────────────────────────────
export function Input({ label, ...props }) {
  return (
    <div style={{ marginBottom: 14 }}>
      {label && <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: 6 }}>{label}</label>}
      <input style={{
        width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
        borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
        fontFamily: 'var(--font-display)', outline: 'none',
      }} {...props} />
    </div>
  )
}

export function Select({ label, children, ...props }) {
  return (
    <div style={{ marginBottom: 14 }}>
      {label && <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: 6 }}>{label}</label>}
      <select style={{
        width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
        borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
        fontFamily: 'var(--font-display)', outline: 'none',
      }} {...props}>
        {children}
      </select>
    </div>
  )
}

export function Textarea({ label, ...props }) {
  return (
    <div style={{ marginBottom: 14 }}>
      {label && <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'block', marginBottom: 6 }}>{label}</label>}
      <textarea style={{
        width: '100%', background: 'var(--bg3)', border: '1px solid var(--border2)',
        borderRadius: 7, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
        fontFamily: 'var(--font-display)', outline: 'none', resize: 'vertical',
      }} {...props} />
    </div>
  )
}

// ── Section heading ────────────────────────────────────────────────────────
export function SectionHead({ children }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 10 }}>
      {children}
    </div>
  )
}

// ── Stat box ───────────────────────────────────────────────────────────────
export function Stat({ value, label, color }) {
  return (
    <div style={{ textAlign: 'center', padding: '16px 12px', background: 'var(--bg3)', borderRadius: 8 }}>
      <div style={{ fontSize: 32, fontWeight: 800, color: color || 'var(--text)' }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</div>
    </div>
  )
}

// ── Log line ───────────────────────────────────────────────────────────────
export function LogBox({ lines, height = 180 }) {
  const ref = React.useRef()
  React.useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [lines])
  return (
    <div ref={ref} style={{
      background: '#080b12', border: '1px solid var(--border)', borderRadius: 8,
      padding: 14, height, overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11,
    }}>
      {lines.length === 0 && <div style={{ color: 'var(--text3)' }}>— Ready —</div>}
      {lines.map((l, i) => (
        <div key={i} style={{
          padding: '2px 0',
          color: l.type === 'success' ? 'var(--green)' : l.type === 'error' ? 'var(--red)' : l.type === 'warn' ? 'var(--orange)' : '#60a5fa',
        }}>
          [{l.time}] {l.text}
        </div>
      ))}
    </div>
  )
}

// ── Step indicator ─────────────────────────────────────────────────────────
export function Steps({ steps, current }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '14px 0' }}>
      {steps.map(s => {
        const state = s.id === current ? 'running' : s.done ? 'done' : s.error ? 'error' : 'wait'
        const colors = {
          wait:    { bg: 'var(--bg3)', color: 'var(--text3)', border: 'var(--border2)' },
          running: { bg: '#0f1f4a', color: 'var(--blue)', border: 'var(--blue)' },
          done:    { bg: '#052e1c', color: 'var(--green)', border: '#065f46' },
          error:   { bg: '#3d0505', color: 'var(--red)', border: '#991b1b' },
        }
        const c = colors[state]
        return (
          <div key={s.id} style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '4px 12px', borderRadius: 20, fontSize: 11, fontWeight: 700,
            background: c.bg, color: c.color, border: `1px solid ${c.border}`,
            animation: state === 'running' ? 'pulse 1.5s infinite' : 'none',
          }}>
            <span>{s.icon}</span>{s.label}
          </div>
        )
      })}
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}`}</style>
    </div>
  )
}

// ── JSON viewer ────────────────────────────────────────────────────────────
export function JsonBox({ data, height = 280 }) {
  const text = JSON.stringify(data, null, 2)
  return (
    <div style={{
      background: '#080b12', border: '1px solid var(--border)', borderRadius: 8,
      padding: 14, maxHeight: height, overflowY: 'auto',
      fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8faac3',
      whiteSpace: 'pre-wrap', wordBreak: 'break-all',
    }}>
      {text}
    </div>
  )
}

// ── Table ──────────────────────────────────────────────────────────────────
export function Table({ headers, rows, onRowClick }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={i} style={{
                textAlign: 'left', padding: '10px 14px',
                fontSize: 11, fontWeight: 700, color: 'var(--text2)',
                textTransform: 'uppercase', letterSpacing: '0.5px',
                borderBottom: '1px solid var(--border)',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={headers.length} style={{ padding: 24, textAlign: 'center', color: 'var(--text3)' }}>No data yet.</td></tr>
          )}
          {rows.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)} style={{
              borderBottom: '1px solid var(--border)',
              cursor: onRowClick ? 'pointer' : 'default',
              transition: 'background 0.1s',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--bg3)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {row.cells.map((cell, j) => (
                <td key={j} style={{ padding: '12px 14px', color: cell.dim ? 'var(--text2)' : 'var(--text)' }}>
                  {cell.content}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────
export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: '10px 16px', fontSize: 12, fontWeight: 700,
          background: 'none', border: 'none', borderBottom: `2px solid ${active === t ? 'var(--blue)' : 'transparent'}`,
          color: active === t ? 'var(--blue)' : 'var(--text2)',
          cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.5px',
          transition: 'all 0.15s',
        }}>
          {t}
        </button>
      ))}
    </div>
  )
}