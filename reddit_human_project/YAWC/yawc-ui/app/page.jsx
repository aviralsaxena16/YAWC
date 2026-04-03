// YAWC v5 — Production AI Research Agent
// app/page.jsx  (Next.js App Router)
// Features: RAG memory, PDF export, Teach spider, Trace forensics
// NEXT_PUBLIC_API_URL=http://localhost:8000

"use client";
import { useState, useRef, useEffect, useCallback, useId } from "react";

const API = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL)
  || "http://localhost:8000";

// ── Stable chat_id per browser session ───────────────────────────────────────
const SESSION_CHAT_ID = typeof crypto !== "undefined"
  ? crypto.randomUUID()
  : Math.random().toString(36).slice(2);

// ── Global CSS ────────────────────────────────────────────────────────────────
if (typeof document !== "undefined" && !document.getElementById("yawc-v5-styles")) {
  const s = document.createElement("style");
  s.id = "yawc-v5-styles";
  s.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Bricolage+Grotesque:opsz,wght@12..96,300;12..96,400;12..96,500;12..96,700&family=JetBrains+Mono:wght@400;500&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body {
      background: #fff9f7; color: #1a1008;
      font-family: 'Bricolage Grotesque', sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    ::selection { background: #ff4500; color: #fff; }
    ::-webkit-scrollbar { width: 3px; }
    ::-webkit-scrollbar-thumb { background: #ff4500; border-radius: 2px; }

    @keyframes spin    { to { transform: rotate(360deg); } }
    @keyframes fadeUp  { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:none; } }
    @keyframes slideR  { from { opacity:0; transform:translateX(-6px); } to { opacity:1; transform:none; } }
    @keyframes blink   { 0%,100%{opacity:1} 50%{opacity:0} }
    @keyframes dotpop  { 0%,100%{transform:scaleY(.3);opacity:.2} 50%{transform:scaleY(1);opacity:1} }
    @keyframes stripe  { 0%{background-position:-400px 0} 100%{background-position:400px 0} }
    @keyframes imgFade { from{opacity:0;transform:scale(.97)} to{opacity:1;transform:none} }
    @keyframes ragPop  { 0%{transform:scale(.85);opacity:0} 60%{transform:scale(1.04)} 100%{transform:scale(1);opacity:1} }
    @keyframes overlayIn { from{opacity:0} to{opacity:1} }
    @keyframes modalIn { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:none} }

    .fade-up  { animation: fadeUp .35s cubic-bezier(.22,.68,0,1.15) both; }
    .slide-r  { animation: slideR .26s ease both; }

    .chip {
      background: #fff; border: 1.5px solid #e5d8d0; color: #5a3d2b;
      border-radius: 100px; padding: 9px 18px; font-size: 13px;
      font-family: 'Bricolage Grotesque', sans-serif;
      cursor: pointer; transition: all .17s; white-space: nowrap; line-height: 1;
    }
    .chip:hover {
      background: #ff4500; border-color: #ff4500; color: #fff;
      transform: translateY(-2px); box-shadow: 0 5px 16px rgba(255,69,0,.28);
    }

    .src-pill {
      display: inline-flex; align-items: center; gap: 5px;
      background: #fff8f5; border: 1.5px solid #ffd8c8; border-radius: 8px;
      padding: 4px 10px; text-decoration: none; color: #5a3d2b;
      font-size: 11px; font-family: 'JetBrains Mono', monospace;
      transition: all .14s; white-space: nowrap;
    }
    .src-pill:hover { background: #ff4500; border-color: #ff4500; color: #fff; }

    .src-card {
      display: block; background: #fff; border: 1.5px solid #ede0d8;
      border-radius: 12px; padding: 12px 16px; text-decoration: none;
      color: #1a1008; transition: all .17s;
    }
    .src-card:hover { border-color: #ff4500; transform: translateY(-2px); box-shadow: 0 4px 18px rgba(255,69,0,.11); }

    .img-grid-item {
      display: block; text-decoration: none; border-radius: 10px;
      overflow: hidden; border: 1.5px solid #ede0d8; transition: all .17s; background: #f5ede8;
    }
    .img-grid-item:hover { border-color: #ff4500; transform: translateY(-2px); box-shadow: 0 6px 22px rgba(255,69,0,.15); }
    .img-grid-item img { width: 100%; height: 160px; object-fit: cover; display: block; animation: imgFade .4s ease both; }

    .yt-embed-wrap {
      position: relative; width: 100%; padding-bottom: 56.25%;
      border-radius: 12px; overflow: hidden; background: #0d0d0d;
      border: 1.5px solid #ede0d8; margin: 10px 0;
    }
    .yt-embed-wrap iframe { position: absolute; top:0; left:0; width:100%; height:100%; border:none; }

    .mode-btn {
      border-radius: 100px; padding: 7px 18px; font-size: 12px;
      font-family: 'JetBrains Mono', monospace; font-weight: 500;
      cursor: pointer; transition: all .17s; border: 1.5px solid #e5d8d0;
      background: #fff; color: #8a6a58; letter-spacing: .5px; line-height: 1;
    }
    .mode-btn.active { background: #ff4500; border-color: #ff4500; color: #fff; box-shadow: 0 2px 10px rgba(255,69,0,.28); }
    .mode-btn:not(.active):hover { border-color: #ff4500; color: #ff4500; }

    .icon-btn {
      display: inline-flex; align-items: center; gap: 6px;
      background: none; border: 1.5px solid #e5d8d0; border-radius: 10px;
      padding: 7px 14px; font-size: 12px; font-family: 'JetBrains Mono', monospace;
      color: #8a6a58; cursor: pointer; transition: all .16s; white-space: nowrap;
    }
    .icon-btn:hover { border-color: #ff4500; color: #ff4500; }
    .icon-btn:disabled { opacity: .45; cursor: not-allowed; }

    .icon-btn.danger:hover { border-color: #dc2626; color: #dc2626; }
    .icon-btn.success { border-color: #16a34a; color: #16a34a; }

    .send-btn {
      border-radius: 14px; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; width: 50px; height: 50px; transition: all .17s;
    }
    .send-btn:hover:not(:disabled) { transform: scale(1.05); box-shadow: 0 5px 18px rgba(255,69,0,.38); }

    .yawc-ta {
      flex: 1; background: #fff; border: 1.5px solid #e5d8d0; border-radius: 16px;
      padding: 14px 18px; color: #1a1008; font-family: 'Bricolage Grotesque', sans-serif;
      font-size: 15px; line-height: 1.5; resize: none; outline: none;
      min-height: 50px; max-height: 140px; transition: border-color .2s, box-shadow .2s;
    }
    .yawc-ta:focus { border-color: #ff4500; box-shadow: 0 0 0 3px rgba(255,69,0,.1); }
    .yawc-ta::placeholder { color: #c4a898; }
    .yawc-ta:disabled { opacity: .55; cursor: not-allowed; }

    .cite {
      display: inline-block; background: #fff0e8; color: #ff4500;
      padding: 0 5px; border-radius: 5px; font-size: .78em; font-weight: 700;
      font-family: 'JetBrains Mono', monospace; text-decoration: none;
      margin: 0 1px; transition: all .13s; vertical-align: middle;
    }
    .cite:hover { background: #ff4500; color: #fff; }

    /* Platform badge classes */
    .badge-reddit        { background:#fff0e8;  color:#ff4500;  border-color:#ffd8c8; }
    .badge-stackoverflow { background:#fff8ec;  color:#f47f24;  border-color:#fde8c4; }
    .badge-hackernews    { background:#fff8ec;  color:#e06a00;  border-color:#fde4b0; }
    .badge-wikipedia     { background:#f5f5f5;  color:#3d3d3d;  border-color:#d8d8d8; }
    .badge-youtube       { background:#fff0f0;  color:#cc0000;  border-color:#ffd0d0; }
    .badge-pexels        { background:#f0f6ff;  color:#05a081;  border-color:#c0e4dc; }
    .badge-unsplash      { background:#f0f4ff;  color:#2d5be3;  border-color:#c8d8ff; }
    .badge-quora         { background:#fff4f0;  color:#b92b27;  border-color:#ffd8d4; }
    .badge-default       { background:#f5ede8;  color:#5a3d2b;  border-color:#e5d8d0; }

    /* RAG memory indicator */
    .rag-badge {
      display: inline-flex; align-items: center; gap: 7px;
      background: linear-gradient(135deg, #e8f5e9, #f1f8e9);
      border: 1.5px solid #a5d6a7; border-radius: 100px;
      padding: 5px 14px; font-family: 'JetBrains Mono', monospace;
      font-size: 10px; color: #2e7d32; letter-spacing: 1px;
      animation: ragPop .45s cubic-bezier(.22,.68,0,1.2) both;
    }
    .rag-dot { width:7px; height:7px; border-radius:50%; background:#4caf50; box-shadow:0 0 6px #4caf50; }

    .cursor { display:inline-block; width:2px; height:1em; background:#ff4500; vertical-align:text-bottom; animation:blink .75s step-end infinite; margin-left:2px; }
    .dot { display:inline-block; width:5px; height:20px; background:#ff4500; border-radius:3px; margin:0 2px; animation:dotpop 1s ease infinite; }

    /* Modal overlay */
    .modal-overlay {
      position: fixed; inset: 0; background: rgba(26,16,8,.55);
      backdrop-filter: blur(4px); z-index: 200;
      display: flex; align-items: center; justify-content: center;
      animation: overlayIn .2s ease both;
    }
    .modal-box {
      background: #fff9f7; border: 1.5px solid #ede0d8; border-radius: 20px;
      padding: 32px; width: 480px; max-width: calc(100vw - 48px);
      box-shadow: 0 24px 80px rgba(0,0,0,.18);
      animation: modalIn .3s cubic-bezier(.22,.68,0,1.15) both;
    }
    .modal-title {
      font-family: 'Bebas Neue', sans-serif; font-size: 28px;
      letter-spacing: 3px; color: #1a1008; margin-bottom: 8px;
    }
    .modal-input {
      width: 100%; background: #fff; border: 1.5px solid #e5d8d0;
      border-radius: 12px; padding: 12px 16px; color: #1a1008;
      font-family: 'Bricolage Grotesque', sans-serif; font-size: 14px;
      outline: none; margin: 12px 0; transition: border-color .2s;
    }
    .modal-input:focus { border-color: #ff4500; }
    .modal-primary-btn {
      background: linear-gradient(135deg, #ff4500, #ff6a2f);
      color: #fff; border: none; border-radius: 12px;
      padding: 11px 24px; font-family: 'Bricolage Grotesque', sans-serif;
      font-size: 14px; font-weight: 600; cursor: pointer; transition: all .17s;
    }
    .modal-primary-btn:hover { box-shadow: 0 5px 18px rgba(255,69,0,.35); transform: translateY(-1px); }
    .modal-primary-btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
    .modal-secondary-btn {
      background: none; border: 1.5px solid #e5d8d0; border-radius: 12px;
      padding: 11px 20px; font-family: 'Bricolage Grotesque', sans-serif;
      font-size: 14px; color: #8a6a58; cursor: pointer; transition: all .17s;
    }
    .modal-secondary-btn:hover { border-color: #b8a099; }
  `;
  document.head.appendChild(s);
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:   "#fff9f7", wht: "#ffffff", bdr: "#ede0d8",
  red:  "#ff4500", rdim: "#fff0e8", ink: "#1a1008",
  brn:  "#5a3d2b", mut: "#b8a099",
  ff:   "'Bricolage Grotesque', sans-serif",
  mono: "'JetBrains Mono', monospace",
  head: "'Bebas Neue', sans-serif",
};

// ── Platform metadata ─────────────────────────────────────────────────────────
const PLATFORM_META = {
  "Reddit":        { icon: "🔴", cls: "badge-reddit",        label: "Reddit" },
  "StackOverflow": { icon: "🟠", cls: "badge-stackoverflow",  label: "Stack Overflow" },
  "Hacker News":   { icon: "🟡", cls: "badge-hackernews",    label: "Hacker News" },
  "Wikipedia":     { icon: "📖", cls: "badge-wikipedia",      label: "Wikipedia" },
  "YouTube":       { icon: "▶",  cls: "badge-youtube",        label: "YouTube" },
  "Quora":         { icon: "❓", cls: "badge-quora",          label: "Quora" },
  "Images":        { icon: "📷", cls: "badge-unsplash",       label: "Images" },
  "Unsplash":      { icon: "📷", cls: "badge-unsplash",       label: "Unsplash" },
  "Pexels":        { icon: "🖼️", cls: "badge-pexels",        label: "Pexels" },
};
const INTENT_META = {
  VIDEO: { emoji: "🎬", label: "Video Research", bg: "#fff0f0", color: "#cc0000" },
  IMAGE: { emoji: "🖼️", label: "Image Search",   bg: "#f0f4ff", color: "#2d5be3" },
  TEXT:  { emoji: "📄", label: "Web Research",   bg: "#fff0e8", color: "#ff4500" },
};
function getPM(platform) {
  return PLATFORM_META[platform] || { icon: "🌐", cls: "badge-default", label: platform || "Web" };
}

// ═════════════════════════════════════════════════════════════════════════════
export default function YAWCApp() {
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState("");
  const [mode,        setMode]        = useState("quick");
  const [loading,     setLoading]     = useState(false);
  const [statusMsg,   setStatusMsg]   = useState("");
  const [teachOpen,   setTeachOpen]   = useState(false);
  const bottomRef = useRef(null);
  const textRef   = useRef(null);
  const esRef     = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMsg]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput(""); setLoading(true); setStatusMsg("");
    setMessages(p => [...p, { role: "user", content: q, mode }]);

    const aid = Date.now();
    setMessages(p => [...p, {
      role: "assistant", content: "", sources: [],
      intent: null, ragHit: false, streaming: true, id: aid,
      traceFile: null,
    }]);

    if (esRef.current) esRef.current.close();

    const url = `${API}/api/search?q=${encodeURIComponent(q)}&mode=${mode}&chat_id=${SESSION_CHAT_ID}`;
    const es  = new EventSource(url);
    esRef.current = es;

    es.addEventListener("status",  e => setStatusMsg(JSON.parse(e.data).message));

    es.addEventListener("routing", e => {
      const { query_intent, media_intent, platforms } = JSON.parse(e.data);
      setMessages(p => p.map(m => m.id === aid
        ? { ...m, queryIntent: query_intent, intent: media_intent, platforms }
        : m
      ));
    });

    es.addEventListener("rag_hit", e => {
      const { chunks_used } = JSON.parse(e.data);
      setStatusMsg("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, ragHit: true, ragChunks: chunks_used } : m));
    });

    es.addEventListener("sources", e => {
      const { sources, media_intent } = JSON.parse(e.data);
      setMessages(p => p.map(m => m.id === aid
        ? { ...m, sources, intent: media_intent || m.intent }
        : m
      ));
    });

    es.addEventListener("token", e => {
      const { token } = JSON.parse(e.data);
      setStatusMsg("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: m.content + token } : m));
    });

    es.addEventListener("done", () => {
      setMessages(p => p.map(m => m.id === aid ? { ...m, streaming: false } : m));
      setLoading(false); setStatusMsg(""); es.close();
    });

    es.addEventListener("error", e => {
      let msg = "Something went wrong.", traceFile = null;
      try { const d = JSON.parse(e.data); msg = d.message; traceFile = d.trace_file || null; } catch (_) {}
      setMessages(p => p.map(m => m.id === aid
        ? { ...m, streaming: false, error: msg, traceFile }
        : m
      ));
      setLoading(false); setStatusMsg(""); es.close();
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return;
      setMessages(p => p.map(m => m.id === aid
        ? { ...m, streaming: false, error: "Connection lost — is the backend running on port 8000?" }
        : m
      ));
      setLoading(false); setStatusMsg(""); es.close();
    };
  }, [input, loading, mode]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: T.bg }}>
      <div style={{ height: 3, background: "linear-gradient(90deg,#ff4500,#ff9a3c,#ff6a2f,#ff4500)", backgroundSize: "300% 100%", animation: "stripe 4s linear infinite" }} />
      <TopBar onTeach={() => setTeachOpen(true)} />

      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {isEmpty
          ? <Hero onPick={s => { setInput(s); textRef.current?.focus(); }} />
          : (
            <div style={{ flex: 1, maxWidth: 880, width: "100%", margin: "0 auto", padding: "36px 24px 0", display: "flex", flexDirection: "column", gap: 28 }}>
              {messages.map((m, i) => (
                <Bubble key={m.id || i} msg={m} statusMsg={statusMsg} chatId={SESSION_CHAT_ID} />
              ))}
              {loading && statusMsg && !messages.some(m => m.streaming && m.content) && (
                <ThinkingBubble msg={statusMsg} />
              )}
              <div ref={bottomRef} style={{ height: 24 }} />
            </div>
          )
        }
      </main>

      <InputBar
        value={input} onChange={setInput} onSend={send}
        loading={loading} mode={mode} setMode={setMode}
        textRef={textRef} statusMsg={statusMsg}
        onTeach={() => setTeachOpen(true)}
      />

      {teachOpen && <TeachModal onClose={() => setTeachOpen(false)} />}
    </div>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────
function TopBar({ onTeach }) {
  return (
    <nav style={{ background: T.wht, borderBottom: `1px solid ${T.bdr}`, position: "sticky", top: 0, zIndex: 50 }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 28px", height: 58, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/YAWC_LOGO.png" alt="YAWC" style={{ width: 32, height: 32, borderRadius: 7 }} />
          <span style={{ fontFamily: T.head, fontSize: 27, letterSpacing: 2, color: T.ink, lineHeight: 1 }}>YAWC</span>
          <div style={{ width: 1, height: 16, background: T.bdr, margin: "0 6px" }} />
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>Yet Another Web Crawler</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="icon-btn" onClick={onTeach} title="Open Playwright Codegen to teach YAWC a new spider">
            🧠 Teach YAWC
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 7, background: T.rdim, borderRadius: 100, padding: "5px 14px" }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#16a34a", boxShadow: "0 0 7px #16a34a" }} />
            <span style={{ fontFamily: T.mono, fontSize: 9, color: T.brn, letterSpacing: 1.5, textTransform: "uppercase" }}>live</span>
          </div>
        </div>
      </div>
    </nav>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────────
function Hero({ onPick }) {
  const suggestions = [
    "Best mechanical keyboard under $150?",
    "How does React Server Components work?",
    "How to deal with developer burnout?",
    "Rust async programming tutorial",
    "Minimalist home office setup ideas",
    "MacBook Pro vs Dell XPS for devs?",
    "Espresso machine recommendations?",
    "Best budget GPU for gaming 2025?",
  ];
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", padding: "52px 24px 150px", textAlign: "center" }}>
      <div style={{ position: "relative", marginBottom: 28 }}>
        <div style={{ position: "absolute", inset: -18, borderRadius: "50%", background: "radial-gradient(circle, rgba(255,69,0,.15) 0%, transparent 68%)", filter: "blur(10px)" }} />
        <img src="/YAWC_LOGO.png" alt="YAWC" style={{ width: 96, height: 96, borderRadius: 22, position: "relative", zIndex: 1, boxShadow: "0 18px 52px rgba(255,69,0,.24)" }} />
      </div>
      <h1 style={{ fontFamily: T.head, fontSize: "clamp(56px,10vw,96px)", letterSpacing: 5, lineHeight: 0.93, color: T.ink, textTransform: "uppercase", marginBottom: 18 }}>
        Yet Another<br /><span style={{ color: T.red }}>Web Crawler</span>
      </h1>
      {/* Feature pills */}
      <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap", justifyContent: "center" }}>
        {[
          { icon: "🧠", label: "RAG Memory", color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7" },
          { icon: "📄", label: "PDF Export", color: "#1565c0", bg: "#e3f2fd", border: "#90caf9" },
          { icon: "🎬", label: "Video · Image · Text", color: "#ff4500", bg: "#fff0e8", border: "#ffd8c8" },
          { icon: "🐛", label: "Trace Forensics", color: "#6a1b9a", bg: "#f3e5f5", border: "#ce93d8" },
        ].map((f, i) => (
          <div key={i} style={{
            background: f.bg, color: f.color, border: `1.5px solid ${f.border}`,
            borderRadius: 100, padding: "5px 14px",
            fontFamily: T.mono, fontSize: 10, letterSpacing: 1.5,
            textTransform: "uppercase", display: "flex", alignItems: "center", gap: 5,
          }}>
            <span style={{ fontSize: 12 }}>{f.icon}</span>{f.label}
          </div>
        ))}
      </div>
      <p style={{ fontSize: 15, color: T.brn, lineHeight: 1.85, maxWidth: 480, marginBottom: 40 }}>
        Classifies intent, scrapes 7 platforms in parallel, remembers your conversation, and exports research-grade reports.{" "}
        <strong style={{ color: T.ink }}>Follow-up questions are instant — no re-scraping.</strong>
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 14, width: "100%", maxWidth: 560, marginBottom: 20 }}>
        <div style={{ flex: 1, height: 1, background: T.bdr }} />
        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>try asking</span>
        <div style={{ flex: 1, height: 1, background: T.bdr }} />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 9, justifyContent: "center", maxWidth: 700 }}>
        {suggestions.map((s, i) => <button key={i} className="chip" onClick={() => onPick(s)}>{s}</button>)}
      </div>
    </div>
  );
}

// ── Chat bubble ───────────────────────────────────────────────────────────────
function Bubble({ msg, statusMsg, chatId }) {
  if (msg.role === "user") return (
    <div className="fade-up" style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{
        background: "linear-gradient(135deg,#ff4500,#ff6a2f)", color: "#fff",
        padding: "13px 20px", borderRadius: "20px 20px 4px 20px",
        maxWidth: "68%", fontSize: 15, lineHeight: 1.65, fontFamily: T.ff,
        boxShadow: "0 5px 20px rgba(255,69,0,.24)",
      }}>
        {msg.content}
        {msg.mode === "deep" && (
          <span style={{ marginLeft: 9, background: "rgba(255,255,255,.2)", fontSize: 9, padding: "2px 8px", borderRadius: 10, letterSpacing: 1.5, textTransform: "uppercase", fontFamily: T.mono, verticalAlign: "middle" }}>deep</span>
        )}
      </div>
    </div>
  );

  if (msg.role === "assistant" && msg.error) {
    return (
      <div className="fade-up">
        <div style={{ background: "#fff5f5", border: "1.5px solid #fecaca", color: "#dc2626", padding: "13px 18px", borderRadius: 14, fontSize: 14, fontWeight: 500 }}>
          ⚠ {msg.error}
        </div>
        {msg.traceFile && (
          <TraceDebugPanel chatId={chatId} traceFile={msg.traceFile} />
        )}
      </div>
    );
  }

  return (
    <div className="fade-up" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <img src="/YAWC_LOGO.png" alt="" style={{ width: 34, height: 34, borderRadius: 9, border: `2px solid ${T.bdr}`, flexShrink: 0, marginTop: 4 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Intent badge */}
        {msg.intent && (() => {
          const im = INTENT_META[msg.intent];
          return im ? (
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6, background: im.bg, color: im.color, borderRadius: 100, padding: "4px 14px", fontFamily: T.mono, fontSize: 9, letterSpacing: 2, textTransform: "uppercase", marginBottom: 10 }}>
              <span>{im.emoji}</span><span>{im.label}</span>
              {msg.queryIntent === "FOLLOW_UP" && (
                <span style={{ opacity: .7 }}>· from memory</span>
              )}
            </div>
          ) : null;
        })()}

        {/* RAG memory badge */}
        {msg.ragHit && (
          <div className="rag-badge" style={{ marginBottom: 10 }}>
            <span className="rag-dot" />
            ⚡ Instant answer — {msg.ragChunks} memory chunks · no scraping needed
          </div>
        )}

        {/* Platforms used */}
        {msg.platforms?.length > 0 && !msg.ragHit && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
            {msg.platforms.map((p, i) => {
              const pm = getPM(p.charAt(0).toUpperCase() + p.slice(1));
              return (
                <span key={i} className={`src-pill ${pm.cls}`} style={{ cursor: "default" }}>
                  {pm.icon} {pm.label}
                </span>
              );
            })}
          </div>
        )}

        {/* Sources */}
        {msg.sources?.length > 0 && (
          <SourcePills sources={msg.sources} intent={msg.intent} />
        )}

        {/* Streaming status */}
        {msg.streaming && statusMsg && !msg.content && (
          <div style={{ fontFamily: T.mono, fontSize: 12, color: T.mut, fontStyle: "italic", marginBottom: 10 }}>{statusMsg}</div>
        )}

        {/* Answer content */}
        {(msg.content || msg.streaming) && (
          <div style={{
            background: T.wht, border: `1.5px solid ${T.bdr}`,
            borderRadius: "4px 18px 18px 18px",
            padding: "18px 22px", fontSize: 15, lineHeight: 1.85,
            fontFamily: T.ff, color: T.ink, boxShadow: "0 2px 12px rgba(0,0,0,.04)",
          }}>
            <MDText text={msg.content} sources={msg.sources || []} />
            {msg.streaming && <span className="cursor" />}
          </div>
        )}

        {/* Post-answer action bar */}
        {!msg.streaming && msg.content && (
          <ActionBar msg={msg} chatId={chatId} />
        )}
      </div>
    </div>
  );
}

function ThinkingBubble({ msg }) {
  return (
    <div className="fade-up" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <img src="/YAWC_LOGO.png" alt="" style={{ width: 34, height: 34, borderRadius: 9, border: `2px solid ${T.bdr}`, opacity: .55, flexShrink: 0, marginTop: 4 }} />
      <div style={{ background: T.wht, border: `1.5px solid ${T.bdr}`, borderRadius: "4px 18px 18px 18px", padding: "16px 20px", display: "flex", alignItems: "center", gap: 8 }}>
        <span className="dot" style={{ animationDelay: "0s" }} />
        <span className="dot" style={{ animationDelay: ".14s" }} />
        <span className="dot" style={{ animationDelay: ".28s" }} />
        <span style={{ fontFamily: T.mono, fontSize: 12, color: T.red, fontStyle: "italic", marginLeft: 8 }}>{msg}</span>
      </div>
    </div>
  );
}

// ── Action bar (PDF + trace) ───────────────────────────────────────────────────
function ActionBar({ msg, chatId }) {
  const [pdfState, setPdfState] = useState("idle"); // idle | loading | done | error

  const handlePDF = async () => {
    setPdfState("loading");
    try {
      const res = await fetch(`${API}/api/export-pdf`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id:  chatId,
          markdown: msg.content,
          title:    "YAWC Research Report",
          query:    msg.query || "",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `yawc-report-${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setPdfState("done");
      setTimeout(() => setPdfState("idle"), 3000);
    } catch (e) {
      console.error("PDF error:", e);
      setPdfState("error");
      setTimeout(() => setPdfState("idle"), 3000);
    }
  };

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
      <button
        className={`icon-btn ${pdfState === "done" ? "success" : pdfState === "error" ? "danger" : ""}`}
        onClick={handlePDF}
        disabled={pdfState === "loading"}
      >
        {pdfState === "loading" && (
          <span style={{ width: 12, height: 12, border: "2px solid currentColor", borderTopColor: "transparent", borderRadius: "50%", display: "inline-block", animation: "spin .65s linear infinite" }} />
        )}
        {pdfState === "idle"    && "📥"}
        {pdfState === "done"    && "✓"}
        {pdfState === "error"   && "✗"}
        {pdfState === "loading" ? " Generating PDF…"
          : pdfState === "done"  ? " PDF Downloaded"
          : pdfState === "error" ? " PDF Failed"
          : " Export PDF"}
      </button>
    </div>
  );
}

// ── Trace debug panel (shown on error with trace_file) ────────────────────────
function TraceDebugPanel({ chatId, traceFile }) {
  const [state, setState] = useState("idle"); // idle | launching | done | error

  const handleView = async () => {
    setState("launching");
    try {
      const res  = await fetch(`${API}/api/traces/${chatId}/view/${traceFile}`, { method: "POST" });
      const data = await res.json();
      setState("done");
    } catch (e) {
      setState("error");
    }
    setTimeout(() => setState("idle"), 5000);
  };

  const handleDownload = () => {
    window.open(`${API}/api/traces/${chatId}/download/${traceFile}`, "_blank");
  };

  return (
    <div style={{
      marginTop: 10, background: "#f8f0ff", border: "1.5px solid #ce93d8",
      borderRadius: 12, padding: "12px 16px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 16 }}>🐛</span>
        <span style={{ fontFamily: T.mono, fontSize: 11, color: "#6a1b9a", letterSpacing: 1, textTransform: "uppercase" }}>
          Crash Forensics Available
        </span>
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: "#7b1fa2", marginBottom: 10 }}>
        Trace file: <strong>{traceFile}</strong>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          className="icon-btn"
          onClick={handleView}
          disabled={state === "launching"}
          style={{ borderColor: "#ce93d8", color: "#6a1b9a" }}
        >
          {state === "launching" ? "⏳ Launching…" : state === "done" ? "✓ Opened" : "🔍 Open in Trace Viewer"}
        </button>
        <button
          className="icon-btn"
          onClick={handleDownload}
          style={{ borderColor: "#ce93d8", color: "#6a1b9a" }}
        >
          ⬇ Download trace.zip
        </button>
      </div>
      {state === "done" && (
        <div style={{ marginTop: 8, fontFamily: T.mono, fontSize: 10, color: "#388e3c" }}>
          ✓ Playwright Trace Viewer opened at http://localhost:9323
        </div>
      )}
    </div>
  );
}

// ── Source pills ──────────────────────────────────────────────────────────────
function SourcePills({ sources, intent }) {
  const [expanded, setExpanded] = useState(false);

  if (intent === "IMAGE") {
    return <ImageSourceGrid sources={sources} />;
  }

  const show = expanded ? sources : sources.slice(0, 5);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: expanded ? 10 : 0 }}>
        {show.map((s, i) => {
          const pm = getPM(s.platform);
          return (
            <a key={i} href={s.url} target="_blank" rel="noreferrer"
               className={`src-pill slide-r ${pm.cls}`}
               style={{ animationDelay: `${i * .05}s` }}>
              <span style={{ fontSize: 11 }}>{pm.icon}</span>
              <span style={{ fontWeight: 700 }}>[{s.index}]</span>
              <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.channel || s.title?.slice(0, 26) || pm.label}
              </span>
              {s.score && s.score !== "0" && s.score !== "N/A" && (
                <span style={{ opacity: .7 }}>↑{s.score}</span>
              )}
            </a>
          );
        })}
        {!expanded && sources.length > 5 && (
          <button onClick={() => setExpanded(true)} style={{ background: "none", border: `1.5px solid ${T.bdr}`, color: T.mut, borderRadius: 8, padding: "4px 10px", fontSize: 11, cursor: "pointer", fontFamily: T.mono }}>
            +{sources.length - 5} more ↓
          </button>
        )}
      </div>
      {expanded && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {sources.map((s, i) => {
              const pm = getPM(s.platform);
              return (
                <a key={i} href={s.url} target="_blank" rel="noreferrer" className="src-card">
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                    <span className={`src-pill ${pm.cls}`} style={{ fontSize: 9, padding: "2px 8px", cursor: "default" }}>
                      {pm.icon} {pm.label}
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut }}>[{s.index}]</span>
                  </div>
                  {s.platform === "YouTube" && s.thumbnail && (
                    <img src={s.thumbnail} alt={s.title} style={{ width: "100%", height: 80, objectFit: "cover", borderRadius: 6, marginBottom: 6 }} loading="lazy" />
                  )}
                  <div style={{ fontSize: 12, lineHeight: 1.45, marginBottom: 4, fontWeight: 500 }}>{s.title}</div>
                  {s.channel && <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut }}>{s.channel}</div>}
                  {s.score && s.score !== "0" && s.score !== "N/A" && (
                    <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, marginTop: 2 }}>↑ {s.score}</div>
                  )}
                </a>
              );
            })}
          </div>
          <button onClick={() => setExpanded(false)} style={{ marginTop: 8, width: "100%", background: "none", border: `1.5px solid ${T.bdr}`, color: T.mut, padding: "7px", borderRadius: 10, fontSize: 11, cursor: "pointer", fontFamily: T.mono }}>
            ▲ collapse
          </button>
        </div>
      )}
    </div>
  );
}

function ImageSourceGrid({ sources }) {
  const [expanded, setExpanded] = useState(false);
  const show = expanded ? sources : sources.slice(0, 6);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
        {show.map((s, i) => (
          <a key={i} href={s.url} target="_blank" rel="noreferrer" className="img-grid-item">
            <img src={s.image_url} alt={s.alt || "image"} loading="lazy" />
            <div style={{ padding: "5px 8px", fontFamily: T.mono, fontSize: 9, color: T.brn, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
              {getPM(s.platform).icon} [{s.index}] {(s.alt || s.platform || "").slice(0, 22)}
            </div>
          </a>
        ))}
      </div>
      {sources.length > 6 && (
        <button onClick={() => setExpanded(o => !o)} style={{ marginTop: 8, width: "100%", background: "none", border: `1.5px solid ${T.bdr}`, color: T.mut, padding: "7px", borderRadius: 10, fontSize: 11, cursor: "pointer", fontFamily: T.mono }}>
          {expanded ? "▲ collapse" : `▼ show all ${sources.length} images`}
        </button>
      )}
    </div>
  );
}

// ── MDText — full markdown renderer ──────────────────────────────────────────
function MDText({ text, sources = [] }) {
  if (!text) return null;
  const lines = text.split("\n");
  const nodes = [];
  let key = 0;

  for (const line of lines) {
    if (!line.trim()) {
      nodes.push(<div key={key++} style={{ height: 6 }} />);
      continue;
    }
    // YouTube embed
    const ytMatch = line.match(/\[YOUTUBE_EMBED:\s*(https?:\/\/[^\]]+)\]/);
    if (ytMatch) {
      const before = line.slice(0, ytMatch.index).trim();
      const after  = line.slice(ytMatch.index + ytMatch[0].length).trim();
      nodes.push(
        <div key={key++}>
          {before && <p style={{ margin: "0 0 6px", lineHeight: 1.85 }}>{renderInline(before, sources)}</p>}
          <YouTubeEmbed url={ytMatch[1].trim()} />
          {after  && <p style={{ margin: "6px 0 0", lineHeight: 1.85 }}>{renderInline(after, sources)}</p>}
        </div>
      );
      continue;
    }
    // Full-line image
    const imgMatch = line.match(/^!\[([^\]]*)\]\((https?:\/\/[^)]+)\)$/);
    if (imgMatch) {
      nodes.push(<InlineImage key={key++} src={imgMatch[2]} alt={imgMatch[1]} />);
      continue;
    }
    // Section heading
    if (line.startsWith("## ")) {
      nodes.push(
        <div key={key++} style={{ marginTop: 20, marginBottom: 8 }}>
          <span style={{ fontFamily: T.head, fontSize: 20, letterSpacing: 1.5, color: T.ink, textTransform: "uppercase", borderBottom: `2.5px solid ${T.red}`, paddingBottom: 3 }}>
            {line.slice(3)}
          </span>
        </div>
      );
      continue;
    }
    nodes.push(
      <p key={key++} style={{ margin: "0 0 5px", lineHeight: 1.85 }}>
        {renderInline(line, sources)}
      </p>
    );
  }
  return <div>{nodes}</div>;
}

function renderInline(line, sources) {
  return tokenise(line).map((tok, ti) => {
    if (tok.type === "bold")
      return <strong key={ti} style={{ fontWeight: 700, color: T.ink }}>{tok.text}</strong>;
    if (tok.type === "code")
      return <code key={ti} style={{ background: "#f4ede8", color: "#c94a00", padding: "1px 6px", borderRadius: 5, fontFamily: T.mono, fontSize: "0.86em" }}>{tok.text}</code>;
    if (tok.type === "cite") {
      const src = sources.find(s => s.index === tok.n);
      return <a key={ti} href={src?.url || "#"} target="_blank" rel="noreferrer" className="cite" title={src ? `${src.platform} — ${src.title}` : `Source ${tok.n}`}>[{tok.n}]</a>;
    }
    if (tok.type === "img")
      return <InlineImage key={ti} src={tok.url} alt={tok.alt} compact />;
    return <span key={ti}>{tok.text}</span>;
  });
}

function tokenise(line) {
  const tokens = [], re = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d+)\]|!\[([^\]]*)\]\((https?:\/\/[^)]+)\)/g;
  let last = 0, m;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) tokens.push({ type: "text", text: line.slice(last, m.index) });
    if      (m[1] !== undefined) tokens.push({ type: "bold", text: m[1] });
    else if (m[2] !== undefined) tokens.push({ type: "code", text: m[2] });
    else if (m[3] !== undefined) tokens.push({ type: "cite", n: parseInt(m[3]) });
    else if (m[4] !== undefined) tokens.push({ type: "img", alt: m[4], url: m[5] });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ type: "text", text: line.slice(last) });
  return tokens;
}

function YouTubeEmbed({ url }) {
  let embedUrl = url;
  const wm = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
  if (wm) embedUrl = `https://www.youtube.com/embed/${wm[1]}`;
  const final = embedUrl + (embedUrl.includes("?") ? "&" : "?") + "rel=0&modestbranding=1";
  return (
    <div className="yt-embed-wrap">
      <iframe src={final} title="YouTube video" allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture" allowFullScreen />
    </div>
  );
}

function InlineImage({ src, alt, compact = false }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  if (compact) return (
    <img src={src} alt={alt} onError={() => setFailed(true)}
      style={{ display: "inline-block", maxHeight: 80, maxWidth: 120, objectFit: "cover", borderRadius: 6, margin: "0 4px", verticalAlign: "middle", border: `1px solid ${T.bdr}` }}
      loading="lazy" />
  );
  return (
    <a href={src} target="_blank" rel="noreferrer" style={{ display: "block", margin: "10px 0" }}>
      <img src={src} alt={alt || "image"} onError={() => setFailed(true)}
        style={{ width: "100%", maxHeight: 340, objectFit: "contain", borderRadius: 10, border: `1.5px solid ${T.bdr}`, background: "#f5ede8", animation: "imgFade .4s ease both", cursor: "zoom-in" }}
        loading="lazy" />
      {alt && <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, textAlign: "center", marginTop: 4 }}>{alt}</div>}
    </a>
  );
}

// ── Teach Modal ───────────────────────────────────────────────────────────────
function TeachModal({ onClose }) {
  const [url,        setUrl]        = useState("");
  const [spiderName, setSpiderName] = useState("");
  const [state,      setState]      = useState("idle"); // idle | loading | success | error
  const [result,     setResult]     = useState(null);

  const handleTeach = async () => {
    if (!url.trim()) return;
    setState("loading");
    try {
      const res  = await fetch(`${API}/api/teach`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ url: url.trim(), spider_name: spiderName.trim() }),
      });
      const data = await res.json();
      setResult(data);
      setState(data.status === "success" ? "success" : "error");
    } catch (e) {
      setResult({ message: e.message });
      setState("error");
    }
  };

  const isLoading = state === "loading";

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
          <div className="modal-title">🧠 Teach YAWC</div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: T.mut, lineHeight: 1 }}>✕</button>
        </div>
        <p style={{ fontSize: 13, color: T.brn, lineHeight: 1.7, marginBottom: 16 }}>
          Opens a live Playwright browser on your machine. Interact with the target site — YAWC records your actions and generates a Scrapy spider scaffold automatically.
        </p>

        <label style={{ fontSize: 12, fontFamily: T.mono, color: T.mut, letterSpacing: 1, textTransform: "uppercase" }}>Target URL</label>
        <input
          className="modal-input"
          type="url"
          placeholder="https://example.com/search"
          value={url}
          onChange={e => setUrl(e.target.value)}
          disabled={isLoading}
        />

        <label style={{ fontSize: 12, fontFamily: T.mono, color: T.mut, letterSpacing: 1, textTransform: "uppercase" }}>Spider Name (optional)</label>
        <input
          className="modal-input"
          type="text"
          placeholder="e.g. my_forum"
          value={spiderName}
          onChange={e => setSpiderName(e.target.value)}
          disabled={isLoading}
          style={{ marginBottom: 20 }}
        />

        {state === "idle" || state === "loading" ? (
          <div style={{ display: "flex", gap: 10 }}>
            <button className="modal-primary-btn" onClick={handleTeach} disabled={!url.trim() || isLoading}>
              {isLoading
                ? <><span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid rgba(255,255,255,.4)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin .65s linear infinite", marginRight: 8, verticalAlign: "middle" }} />Recording…</>
                : "🎬 Open Playwright & Record"
              }
            </button>
            <button className="modal-secondary-btn" onClick={onClose} disabled={isLoading}>Cancel</button>
          </div>
        ) : state === "success" ? (
          <div>
            <div style={{ background: "#e8f5e9", border: "1.5px solid #a5d6a7", borderRadius: 10, padding: "12px 16px", marginBottom: 14 }}>
              <div style={{ fontFamily: T.mono, fontSize: 11, color: "#2e7d32", marginBottom: 6 }}>✓ Spider scaffold generated</div>
              <div style={{ fontFamily: T.mono, fontSize: 10, color: "#388e3c" }}>Scaffold: {result?.scaffold}</div>
              <div style={{ fontFamily: T.mono, fontSize: 10, color: "#388e3c" }}>Codegen: {result?.out_file}</div>
            </div>
            {result?.code_preview && (
              <pre style={{ background: "#f5ede8", border: `1px solid ${T.bdr}`, borderRadius: 8, padding: "10px 12px", fontSize: 10, fontFamily: T.mono, color: T.brn, overflow: "auto", maxHeight: 180, marginBottom: 14 }}>
                {result.code_preview}
              </pre>
            )}
            <button className="modal-secondary-btn" onClick={onClose}>Close</button>
          </div>
        ) : (
          <div>
            <div style={{ background: "#fff5f5", border: "1.5px solid #fecaca", borderRadius: 10, padding: "12px 16px", marginBottom: 14, fontFamily: T.mono, fontSize: 11, color: "#dc2626" }}>
              ✗ {result?.message || "Something went wrong"}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button className="modal-primary-btn" onClick={() => setState("idle")}>Try Again</button>
              <button className="modal-secondary-btn" onClick={onClose}>Close</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Input bar ─────────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSend, loading, mode, setMode, textRef, statusMsg, onTeach }) {
  const onKey = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } };

  return (
    <div style={{ position: "sticky", bottom: 0, zIndex: 40, background: "rgba(255,249,247,.97)", backdropFilter: "blur(18px)", borderTop: `1px solid ${T.bdr}`, padding: "12px 24px 18px" }}>
      {/* Mode row */}
      <div style={{ maxWidth: 880, margin: "0 auto 10px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>MODE</span>
        {[
          { id: "quick", icon: "⚡", label: "Quick",  hint: "~15s" },
          { id: "deep",  icon: "🔬", label: "Deep",   hint: "~60s" },
        ].map(m => (
          <button key={m.id} className={`mode-btn${mode === m.id ? " active" : ""}`} onClick={() => setMode(m.id)} title={m.hint}>
            {m.icon} {m.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button className="icon-btn" onClick={onTeach}>🧠 Teach</button>
        {loading && statusMsg && (
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.red, fontStyle: "italic" }}>{statusMsg}</span>
        )}
      </div>

      {/* Input + send */}
      <div style={{ maxWidth: 880, margin: "0 auto", display: "flex", gap: 10, alignItems: "flex-end" }}>
        <textarea
          ref={textRef}
          className="yawc-ta"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask anything — or follow up on what was already found…"
          disabled={loading}
          rows={1}
        />
        <button className="send-btn" onClick={onSend} disabled={loading || !value.trim()}
          style={{ background: loading || !value.trim() ? "#e8ddd8" : "linear-gradient(135deg,#ff4500,#ff6a2f)" }}>
          {loading
            ? <div style={{ width: 18, height: 18, border: "2.5px solid rgba(255,255,255,.35)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin .65s linear infinite" }} />
            : <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke={loading || !value.trim() ? "#b8a099" : "#fff"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
          }
        </button>
      </div>

      {/* Hints */}
      <div style={{ maxWidth: 880, margin: "7px auto 0", fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: .8, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <span>↵ Search</span>
        <span>Shift+↵ newline</span>
        <span>🧠 Follow-ups answered from memory</span>
        <span>7 platforms auto-selected</span>
      </div>
    </div>
  );
}
