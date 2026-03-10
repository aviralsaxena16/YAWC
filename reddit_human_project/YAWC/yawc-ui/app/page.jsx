// YAWC — Yet Another Web Crawler  |  Chat UI  |  Next.js / React
// Place this in:  app/page.jsx  (Next.js App Router)
// Set env var:    NEXT_PUBLIC_API_URL=http://localhost:8000

"use client";
import { useState, useRef, useEffect } from "react";

const LOGO = "data:image/jpeg;base64,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";
const API  = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) || "http://localhost:8000";

// ── Inject fonts + keyframes once ────────────────────────────────────────────
if (typeof document !== "undefined" && !document.getElementById("yawc-styles")) {
  const s = document.createElement("style");
  s.id = "yawc-styles";
  s.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,400;0,500;1,400&display=swap');
    *,*::before,*::after{box-sizing:border-box}
    body{margin:0;background:#0d0d0d;color:#e8e8e8}
    ::-webkit-scrollbar{width:5px}
    ::-webkit-scrollbar-track{background:#0d0d0d}
    ::-webkit-scrollbar-thumb{background:#2a2a2a;border-radius:3px}
    @keyframes spin  {to{transform:rotate(360deg)}}
    @keyframes pulse {0%,100%{opacity:.2;transform:scale(.7)} 50%{opacity:1;transform:scale(1)}}
    @keyframes fadein{from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)}}
    .msg-anim{animation:fadein .3s ease both}
    textarea:focus{border-color:#ff4500!important;box-shadow:0 0 0 2px rgba(255,69,0,.15)!important}
    .sugg-btn:hover{border-color:#ff4500!important;color:#ff4500!important}
    .src-card:hover{border-color:#ff4500!important}
    .send-btn:hover:not(:disabled){background:#e03e00!important}
    .toggle-btn:hover{color:#ff6633!important}
  `;
  document.head.appendChild(s);
}

// ── Theme constants ───────────────────────────────────────────────────────────
const C = {
  bg:     "#0d0d0d",
  card:   "#141414",
  border: "#252525",
  orange: "#ff4500",
  text:   "#e8e8e8",
  muted:  "#666",
  ff:     '"DM Mono","IBM Plex Mono",monospace',
};

// ── Main component ────────────────────────────────────────────────────────────
export default function YAWCChat() {
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [status,    setStatus]    = useState("");
  const bottomRef = useRef(null);
  const textRef   = useRef(null);
  const esRef     = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, status]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput(""); setLoading(true); setStatus("");
    setMessages(p => [...p, { role: "user", content: q }]);

    if (esRef.current) { esRef.current.close(); }
    const es = new EventSource(`${API}/api/search?q=${encodeURIComponent(q)}`);
    esRef.current = es;

    es.addEventListener("status", e => setStatus(JSON.parse(e.data).message));
    es.addEventListener("result", e => {
      const d = JSON.parse(e.data);
      setMessages(p => [...p, { role: "assistant", content: d.answer, sources: d.sources }]);
      setStatus(""); setLoading(false); es.close();
    });
    es.addEventListener("error", e => {
      let msg = "Something went wrong.";
      try { msg = JSON.parse(e.data).message; } catch(_) {}
      setMessages(p => [...p, { role: "error", content: msg }]);
      setStatus(""); setLoading(false); es.close();
    });
    es.onerror = () => {
      setMessages(p => [...p, { role: "error", content: "Connection lost — is the backend running?" }]);
      setStatus(""); setLoading(false); es.close();
    };
  };

  return (
    <div style={{ fontFamily: C.ff, background: C.bg, minHeight: "100vh",
                   display: "flex", flexDirection: "column", color: C.text }}>
      <Header />
      <main style={{ flex: 1, overflowY: "auto", padding: "28px 0 0" }}>
        {messages.length === 0 && !loading
          ? <EmptyState onPick={s => { setInput(s); textRef.current?.focus(); }} />
          : (
            <div style={{ maxWidth: 780, margin: "0 auto", padding: "0 20px",
                           display: "flex", flexDirection: "column", gap: 28 }}>
              {messages.map((m, i) => <Bubble key={i} msg={m} />)}
              {loading && status && <StatusBubble msg={status} />}
              <div ref={bottomRef} style={{ height: 16 }} />
            </div>
          )
        }
      </main>
      <InputBar
        value={input} onChange={setInput} onSend={send}
        loading={loading} textRef={textRef}
      />
    </div>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────
function Header() {
  return (
    <header style={{
      borderBottom: `1px solid ${C.border}`,
      background: "rgba(13,13,13,0.96)",
      backdropFilter: "blur(14px)",
      position: "sticky", top: 0, zIndex: 20,
    }}>
      <div style={{ maxWidth: 780, margin: "0 auto", padding: "11px 20px",
                     display: "flex", alignItems: "center", gap: 12 }}>
        <img src={LOGO} alt="YAWC" style={{ width: 38, height: 38, borderRadius: 8, flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase" }}>YAWC</div>
          <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2, textTransform: "uppercase" }}>yet another web crawler</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: "#22c55e",
            boxShadow: "0 0 6px #22c55e",
          }} />
          <span style={{ fontSize: 10, color: C.muted, letterSpacing: 1, textTransform: "uppercase" }}>live search</span>
        </div>
      </div>
    </header>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState({ onPick }) {
  const suggestions = [
    "Best mechanical keyboards under $150?",
    "What do Redditors think about Rust vs Go?",
    "How to deal with developer burnout?",
    "Best budget GPU for gaming 2025?",
    "Is learning Vim still worth it?",
    "Top-rated espresso machines for home use?",
  ];
  return (
    <div style={{ maxWidth: 600, margin: "64px auto 0", padding: "0 20px", textAlign: "center" }}>
      <img src={LOGO} alt="" style={{ width: 68, height: 68, borderRadius: 14, marginBottom: 20 }} />
      <h1 style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.5, margin: "0 0 12px", color: C.text }}>
        Ask Reddit. Instantly.
      </h1>
      <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.8, margin: "0 0 32px", maxWidth: 440, marginLeft: "auto", marginRight: "auto" }}>
        YAWC fires up a headless browser, scrapes real Reddit posts live,
        and synthesizes a research-grade answer — no paywalls, no hallucinations.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
        {suggestions.map((s, i) => (
          <button key={i} className="sugg-btn" onClick={() => onPick(s)} style={{
            background: C.card, border: `1px solid ${C.border}`,
            color: C.text, borderRadius: 20, padding: "7px 15px",
            fontSize: 12, cursor: "pointer", transition: "border-color .2s, color .2s",
            fontFamily: C.ff,
          }}>{s}</button>
        ))}
      </div>
    </div>
  );
}

// ── Chat bubbles ──────────────────────────────────────────────────────────────
function Bubble({ msg }) {
  if (msg.role === "user") return (
    <div className="msg-anim" style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{
        background: C.orange, color: "#fff",
        padding: "11px 17px", borderRadius: "18px 18px 4px 18px",
        maxWidth: "72%", fontSize: 14, lineHeight: 1.65,
      }}>{msg.content}</div>
    </div>
  );

  if (msg.role === "error") return (
    <div className="msg-anim" style={{
      background: "#180a0a", border: "1px solid #3d1010",
      color: "#ff6b6b", padding: "11px 16px", borderRadius: 10, fontSize: 13,
    }}>⚠ {msg.content}</div>
  );

  return (
    <div className="msg-anim" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <img src={LOGO} alt="" style={{ width: 30, height: 30, borderRadius: 6, flexShrink: 0, marginTop: 3 }} />
      <div style={{ flex: 1 }}>
        <div style={{
          background: C.card, border: `1px solid ${C.border}`,
          padding: "14px 18px", borderRadius: "4px 18px 18px 18px",
          fontSize: 14, lineHeight: 1.75,
        }}>
          <MDText text={msg.content} />
        </div>
        {msg.sources?.length > 0 && <Sources list={msg.sources} />}
      </div>
    </div>
  );
}

function StatusBubble({ msg }) {
  const dotStyle = (delay) => ({
    width: 7, height: 7, borderRadius: "50%", background: C.orange,
    display: "inline-block", margin: "0 3px",
    animation: `pulse 1.2s ease-in-out ${delay}s infinite`,
  });
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <img src={LOGO} alt="" style={{ width: 30, height: 30, borderRadius: 6, flexShrink: 0, opacity: .6 }} />
      <div style={{
        background: C.card, border: `1px solid ${C.border}`,
        padding: "12px 16px", borderRadius: "4px 18px 18px 18px",
        display: "flex", alignItems: "center", gap: 6,
      }}>
        <span style={dotStyle(0)} />
        <span style={dotStyle(.2)} />
        <span style={dotStyle(.4)} />
        <span style={{ marginLeft: 8, fontSize: 13, color: C.orange, fontStyle: "italic" }}>{msg}</span>
      </div>
    </div>
  );
}

// ── Sources ───────────────────────────────────────────────────────────────────
function Sources({ list }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 10 }}>
      <button className="toggle-btn" onClick={() => setOpen(o => !o)} style={{
        background: "none", border: `1px solid ${C.border}`,
        color: C.orange, fontSize: 10, letterSpacing: 1, padding: "4px 11px",
        borderRadius: 4, cursor: "pointer", textTransform: "uppercase",
        fontFamily: C.ff, transition: "color .2s",
      }}>{open ? "▲" : "▼"} {list.length} sources</button>
      {open && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          {list.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noreferrer" className="src-card" style={{
              background: C.card, border: `1px solid ${C.border}`,
              borderRadius: 8, padding: "9px 13px", textDecoration: "none",
              color: C.text, width: "calc(50% - 4px)", transition: "border-color .2s",
            }}>
              <div style={{ fontSize: 9, color: C.orange, letterSpacing: 1.5, marginBottom: 3, textTransform: "uppercase" }}>
                {s.subreddit || "reddit"}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.4, marginBottom: 5 }}>{s.title}</div>
              <div style={{ fontSize: 10, color: C.muted }}>↑ {s.score}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Inline markdown ───────────────────────────────────────────────────────────
function MDText({ text }) {
  return (
    <div>
      {text.split(/\n+/).filter(Boolean).map((para, i) => (
        <p key={i} style={{ margin: "0 0 10px" }}>
          {para.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, j) => {
            if (part.startsWith("**") && part.endsWith("**"))
              return <strong key={j}>{part.slice(2,-2)}</strong>;
            if (part.startsWith("`") && part.endsWith("`"))
              return <code key={j} style={{ background:"#1c1c1c", color:"#e06c75",
                padding:"1px 5px", borderRadius:3, fontFamily:C.ff, fontSize:"0.88em" }}>
                {part.slice(1,-1)}
              </code>;
            return part;
          })}
        </p>
      ))}
    </div>
  );
}

// ── Input bar ─────────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSend, loading, textRef }) {
  const onKey = e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
  };
  return (
    <div style={{
      position: "sticky", bottom: 0, zIndex: 10,
      background: "rgba(13,13,13,.97)", backdropFilter: "blur(14px)",
      borderTop: `1px solid ${C.border}`, padding: "14px 20px 18px",
    }}>
      <div style={{ maxWidth: 780, margin: "0 auto", display: "flex", gap: 10, alignItems: "flex-end" }}>
        <textarea
          ref={textRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask anything — YAWC searches Reddit live…"
          disabled={loading}
          rows={1}
          style={{
            flex: 1, background: C.card, border: `1px solid ${C.border}`,
            borderRadius: 12, padding: "11px 15px", color: C.text,
            fontFamily: C.ff, fontSize: 14, lineHeight: 1.5, resize: "none",
            outline: "none", minHeight: 44, maxHeight: 130, transition: "border-color .2s, box-shadow .2s",
          }}
        />
        <button
          className="send-btn"
          onClick={onSend}
          disabled={loading || !value.trim()}
          style={{
            background: C.orange, border: "none", borderRadius: 10,
            width: 44, height: 44, cursor: loading || !value.trim() ? "not-allowed" : "pointer",
            opacity: loading || !value.trim() ? .35 : 1,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0, transition: "background .2s, opacity .2s",
          }}
        >
          {loading
            ? <div style={{ width:18, height:18, border:"2px solid #fff",
                borderTopColor:"transparent", borderRadius:"50%",
                animation:"spin .7s linear infinite" }} />
            : <svg width="19" height="19" viewBox="0 0 24 24" fill="none"
                stroke="white" strokeWidth="2.2">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
          }
        </button>
      </div>
      <div style={{ maxWidth: 780, margin: "5px auto 0", fontSize: 10, color: C.muted, letterSpacing: .8 }}>
        ↵ Enter to search · Shift+↵ for newline · Results scraped live from Reddit
      </div>
    </div>
  );
}
