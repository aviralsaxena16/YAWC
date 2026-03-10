// YAWC — Yet Another Web Crawler  |  Chat UI  |  Next.js / React
// Place this in:  app/page.jsx  (Next.js App Router)
// Set env var:    NEXT_PUBLIC_API_URL=http://localhost:8000

"use client";
import { useState, useRef, useEffect } from "react";

const LOGO = "./YAWC_LOGO.png";
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
