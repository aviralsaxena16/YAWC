// YAWC v4 — Intent-Aware Multi-Platform Chat UI
// app/page.jsx  (Next.js App Router)
// NEXT_PUBLIC_API_URL=http://localhost:8000

"use client";
import { useState, useRef, useEffect, useCallback } from "react";

const API = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) || "http://localhost:8000";

// ── Global CSS ────────────────────────────────────────────────────────────────
if (typeof document !== "undefined" && !document.getElementById("yawc-styles")) {
  const s = document.createElement("style");
  s.id = "yawc-styles";
  s.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Bricolage+Grotesque:opsz,wght@12..96,300;12..96,400;12..96,500;12..96,700;12..96,800&family=JetBrains+Mono:wght@400;500&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { scroll-behavior: smooth; }
    body {
      background: #fff9f7;
      color: #1a1008;
      font-family: 'Bricolage Grotesque', sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    ::selection { background: #ff4500; color: #fff; }
    ::-webkit-scrollbar { width: 3px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #ff4500; border-radius: 2px; }

    @keyframes spin    { to { transform: rotate(360deg); } }
    @keyframes fadeUp  { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
    @keyframes slideR  { from { opacity:0; transform:translateX(-8px); } to { opacity:1; transform:translateX(0); } }
    @keyframes blink   { 0%,100%{opacity:1} 50%{opacity:0} }
    @keyframes dotpop  { 0%,100%{transform:scaleY(.35);opacity:.25} 50%{transform:scaleY(1);opacity:1} }
    @keyframes stripe  { 0%{background-position:-400px 0} 100%{background-position:400px 0} }
    @keyframes imgFade { from{opacity:0;transform:scale(.97)} to{opacity:1;transform:scale(1)} }

    .fade-up { animation: fadeUp .38s cubic-bezier(.22,.68,0,1.15) both; }
    .slide-r { animation: slideR .28s ease both; }

    /* ── Suggestion chips ── */
    .chip {
      background: #fff; border: 1.5px solid #e5d8d0; color: #5a3d2b;
      border-radius: 100px; padding: 9px 18px; font-size: 13px;
      font-family: 'Bricolage Grotesque', sans-serif; font-weight: 400;
      cursor: pointer; transition: all .17s ease; white-space: nowrap; line-height: 1;
    }
    .chip:hover {
      background: #ff4500; border-color: #ff4500; color: #fff;
      transform: translateY(-2px); box-shadow: 0 5px 16px rgba(255,69,0,.28);
    }

    /* ── Source pills (compact, top of bubble) ── */
    .src-pill {
      display: inline-flex; align-items: center; gap: 5px;
      background: #fff8f5; border: 1.5px solid #ffd8c8; border-radius: 8px;
      padding: 4px 10px; text-decoration: none; color: #5a3d2b;
      font-size: 11px; font-family: 'JetBrains Mono', monospace; transition: all .15s;
    }
    .src-pill:hover { background: #ff4500; border-color: #ff4500; color: #fff; transform: translateY(-1px); }

    /* ── Source cards (expanded view) ── */
    .src-card-full {
      display: block; background: #fff; border: 1.5px solid #ede0d8;
      border-radius: 12px; padding: 12px 16px; text-decoration: none; color: #1a1008;
      transition: all .17s;
    }
    .src-card-full:hover { border-color: #ff4500; box-shadow: 0 4px 18px rgba(255,69,0,.11); transform: translateY(-2px); }

    /* ── Image grid items ── */
    .img-grid-item {
      display: block; text-decoration: none; border-radius: 10px;
      overflow: hidden; border: 1.5px solid #ede0d8; transition: all .17s; background: #f5ede8;
    }
    .img-grid-item:hover { border-color: #ff4500; transform: translateY(-2px); box-shadow: 0 6px 22px rgba(255,69,0,.15); }
    .img-grid-item img { width: 100%; height: 160px; object-fit: cover; display: block; animation: imgFade .4s ease both; }

    /* ── YouTube embed wrapper ── */
    .yt-embed-wrap {
      position: relative; width: 100%; padding-bottom: 56.25%;
      border-radius: 12px; overflow: hidden; background: #0d0d0d;
      border: 1.5px solid #ede0d8; margin: 10px 0;
    }
    .yt-embed-wrap iframe {
      position: absolute; top: 0; left: 0;
      width: 100%; height: 100%; border: none;
    }

    /* ── Mode buttons ── */
    .mode-btn {
      border-radius: 100px; padding: 7px 18px; font-size: 12px;
      font-family: 'JetBrains Mono', monospace; font-weight: 500;
      cursor: pointer; transition: all .17s; border: 1.5px solid #e5d8d0;
      background: #fff; color: #8a6a58; letter-spacing: .5px; line-height: 1;
    }
    .mode-btn.active { background: #ff4500; border-color: #ff4500; color: #fff; box-shadow: 0 2px 10px rgba(255,69,0,.28); }
    .mode-btn:not(.active):hover { border-color: #ff4500; color: #ff4500; }

    /* ── Send button ── */
    .send-btn {
      border-radius: 14px; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; width: 50px; height: 50px; transition: all .17s;
    }
    .send-btn:hover:not(:disabled) { transform: scale(1.05); box-shadow: 0 5px 18px rgba(255,69,0,.38); }

    /* ── Textarea ── */
    .yawc-ta {
      flex: 1; background: #fff; border: 1.5px solid #e5d8d0; border-radius: 16px;
      padding: 14px 18px; color: #1a1008; font-family: 'Bricolage Grotesque', sans-serif;
      font-size: 15px; line-height: 1.5; resize: none; outline: none;
      min-height: 50px; max-height: 140px; transition: border-color .2s, box-shadow .2s;
    }
    .yawc-ta:focus { border-color: #ff4500; box-shadow: 0 0 0 3px rgba(255,69,0,.1); }
    .yawc-ta::placeholder { color: #c4a898; }
    .yawc-ta:disabled { opacity:.55; cursor:not-allowed; }

    /* ── Inline citation badge ── */
    .cite {
      display: inline-block; background: #fff0e8; color: #ff4500;
      padding: 0 5px; border-radius: 5px; font-size: .78em; font-weight: 700;
      font-family: 'JetBrains Mono', monospace; text-decoration: none;
      margin: 0 1px; transition: all .13s; vertical-align: middle;
    }
    .cite:hover { background: #ff4500; color: #fff; }

    /* ── Platform badge colors ── */
    .badge-reddit       { background: #fff0e8; color: #ff4500; border: 1.5px solid #ffd8c8; }
    .badge-stackoverflow{ background: #fff8ec; color: #f47f24; border: 1.5px solid #fde8c4; }
    .badge-youtube      { background: #fff0f0; color: #cc0000; border: 1.5px solid #ffd0d0; }
    .badge-pinterest    { background: #fff0f4; color: #e60023; border: 1.5px solid #ffc8d4; }
    .badge-unsplash     { background: #f0f4ff; color: #2d5be3; border: 1.5px solid #c8d8ff; }
    .badge-quora        { background: #fff4f0; color: #b92b27; border: 1.5px solid #ffd8d4; }
    .badge-default      { background: #f5ede8; color: #5a3d2b; border: 1.5px solid #e5d8d0; }

    /* ── Intent badge (shown in message) ── */
    .intent-badge {
      display: inline-flex; align-items: center; gap: 6px;
      border-radius: 100px; padding: 4px 14px;
      font-family: 'JetBrains Mono', monospace; font-size: 9px;
      letter-spacing: 2px; text-transform: uppercase; margin-bottom: 10px;
    }

    .cursor { display:inline-block; width:2px; height:1em; background:#ff4500; vertical-align:text-bottom; animation:blink .75s step-end infinite; margin-left:2px; }
    .dot { display:inline-block; width:5px; height:20px; background:#ff4500; border-radius:3px; margin:0 2px; animation:dotpop 1s ease infinite; }
  `;
  document.head.appendChild(s);
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:   "#fff9f7",
  wht:  "#ffffff",
  bdr:  "#ede0d8",
  red:  "#ff4500",
  rdim: "#fff0e8",
  org:  "#ff6a2f",
  ink:  "#1a1008",
  brn:  "#5a3d2b",
  mut:  "#b8a099",
  ff:   "'Bricolage Grotesque', sans-serif",
  mono: "'JetBrains Mono', monospace",
  head: "'Bebas Neue', sans-serif",
};

// ── Platform metadata ─────────────────────────────────────────────────────────
const PLATFORM_META = {
  Reddit:        { icon: "🔴", cls: "badge-reddit",        label: "Reddit"         },
  StackOverflow: { icon: "🟠", cls: "badge-stackoverflow",  label: "Stack Overflow" },
  YouTube:       { icon: "▶",  cls: "badge-youtube",        label: "YouTube"        },
  Pinterest:     { icon: "📌", cls: "badge-pinterest",      label: "Pinterest"      },
  Unsplash:      { icon: "📷", cls: "badge-unsplash",       label: "Unsplash"       },
  Quora:         { icon: "❓", cls: "badge-quora",           label: "Quora"          },
  Images:        { icon: "🖼️", cls: "badge-unsplash",       label: "Images"         },
};

const INTENT_META = {
  VIDEO: { emoji: "🎬", label: "Video Research",  bg: "#fff0f0", color: "#cc0000" },
  IMAGE: { emoji: "🖼️", label: "Image Search",    bg: "#f0f4ff", color: "#2d5be3" },
  TEXT:  { emoji: "📄", label: "Text Research",   bg: "#fff0e8", color: "#ff4500" },
};

function getPlatformMeta(platform) {
  return PLATFORM_META[platform] || { icon: "🌐", cls: "badge-default", label: platform || "Web" };
}

// ══════════════════════════════════════════════════════════════════════════════
export default function YAWCApp() {
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [mode,      setMode]      = useState("quick");
  const [loading,   setLoading]   = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
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
      intent: null, streaming: true, id: aid,
    }]);

    if (esRef.current) esRef.current.close();
    const es = new EventSource(`${API}/api/search?q=${encodeURIComponent(q)}&mode=${mode}`);
    esRef.current = es;

    // Intent classified by backend
    es.addEventListener("intent", e => {
      const { intent } = JSON.parse(e.data);
      setMessages(p => p.map(m => m.id === aid ? { ...m, intent } : m));
    });

    es.addEventListener("status",  e => setStatusMsg(JSON.parse(e.data).message));

    es.addEventListener("sources", e => {
      const { sources, intent } = JSON.parse(e.data);
      setMessages(p => p.map(m => m.id === aid ? { ...m, sources, intent: intent || m.intent } : m));
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
      let msg = "Something went wrong.";
      try { msg = JSON.parse(e.data).message; } catch (_) {}
      setMessages(p => p.filter(m => m.id !== aid).concat([{ role: "error", content: msg }]));
      setLoading(false); setStatusMsg(""); es.close();
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return;
      setMessages(p => p.filter(m => m.id !== aid).concat([{
        role: "error",
        content: "Connection lost — is the backend running on port 8000?",
      }]));
      setLoading(false); setStatusMsg(""); es.close();
    };
  }, [input, loading, mode]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: T.bg }}>
      <div style={{ height: 3, background: "linear-gradient(90deg,#ff4500,#ff9a3c,#ff6a2f,#ff4500)", backgroundSize: "300% 100%", animation: "stripe 4s linear infinite" }} />
      <TopBar />
      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {isEmpty
          ? <Hero onPick={s => { setInput(s); textRef.current?.focus(); }} />
          : (
            <div style={{ flex: 1, maxWidth: 860, width: "100%", margin: "0 auto", padding: "36px 24px 0", display: "flex", flexDirection: "column", gap: 28 }}>
              {messages.map((m, i) => <Bubble key={m.id || i} msg={m} statusMsg={statusMsg} />)}
              {loading && statusMsg && !messages.some(m => m.streaming && m.content) && <ThinkingBubble msg={statusMsg} />}
              <div ref={bottomRef} style={{ height: 24 }} />
            </div>
          )
        }
      </main>
      <InputBar value={input} onChange={setInput} onSend={send} loading={loading} mode={mode} setMode={setMode} textRef={textRef} statusMsg={statusMsg} />
    </div>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────
function TopBar() {
  return (
    <nav style={{ background: T.wht, borderBottom: `1px solid ${T.bdr}`, position: "sticky", top: 0, zIndex: 50 }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 28px", height: 58, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img src="/YAWC_LOGO.png" alt="YAWC" style={{ width: 32, height: 32, borderRadius: 7 }} />
          <span style={{ fontFamily: T.head, fontSize: 27, letterSpacing: 2, color: T.ink, lineHeight: 1 }}>YAWC</span>
          <div style={{ width: 1, height: 16, background: T.bdr, margin: "0 6px" }} />
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>Yet Another Web Crawler</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 7, background: T.rdim, borderRadius: 100, padding: "5px 14px" }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#16a34a", boxShadow: "0 0 7px #16a34a" }} />
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.brn, letterSpacing: 1.5, textTransform: "uppercase" }}>live search</span>
        </div>
      </div>
    </nav>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────────
function Hero({ onPick }) {
  const suggestions = [
    "Best mechanical keyboard under $150?",
    "React vs Vue — which in 2025?",
    "How to deal with developer burnout?",
    "Best budget GPU for gaming 2025?",
    "Minimalist living room design ideas",
    "Learn Rust tutorial for beginners",
    "Top espresso machines for home use?",
    "Aesthetic desk setup inspiration",
  ];

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", padding: "52px 24px 150px", textAlign: "center" }}>
      <div style={{ position: "relative", marginBottom: 28 }}>
        <div style={{ position: "absolute", inset: -18, borderRadius: "50%", background: "radial-gradient(circle, rgba(255,69,0,.16) 0%, transparent 68%)", filter: "blur(10px)" }} />
        <img src="/YAWC_LOGO.png" alt="YAWC" style={{ width: 96, height: 96, borderRadius: 22, position: "relative", zIndex: 1, boxShadow: "0 18px 52px rgba(255,69,0,.24), 0 4px 14px rgba(0,0,0,.07)" }} />
      </div>

      <h1 style={{ fontFamily: T.head, fontSize: "clamp(58px, 10vw, 100px)", letterSpacing: 5, lineHeight: 0.93, color: T.ink, textTransform: "uppercase", marginBottom: 20 }}>
        Yet Another<br />
        <span style={{ color: T.red }}>Web Crawler</span>
      </h1>

      {/* Intent icons row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", justifyContent: "center" }}>
        {[
          { icon: "📄", label: "Reddit · StackOverflow · Quora", color: "#ff4500", bg: "#fff0e8" },
          { icon: "🎬", label: "YouTube video research",          color: "#cc0000", bg: "#fff0f0" },
          { icon: "🖼️", label: "Unsplash · Pinterest images",    color: "#2d5be3", bg: "#f0f4ff" },
        ].map((m, i) => (
          <div key={i} style={{ background: m.bg, color: m.color, borderRadius: 100, padding: "6px 16px", fontFamily: T.mono, fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 14 }}>{m.icon}</span>{m.label}
          </div>
        ))}
      </div>

      <p style={{ fontSize: 15, color: T.brn, lineHeight: 1.85, maxWidth: 460, marginBottom: 42, fontWeight: 400 }}>
        Spins up a headless browser, classifies your query by intent, scrapes the right platform live, and synthesizes a research-grade answer.{" "}
        <strong style={{ color: T.ink, fontWeight: 700 }}>Videos, images, or text — automatically.</strong>
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 14, width: "100%", maxWidth: 560, marginBottom: 22 }}>
        <div style={{ flex: 1, height: 1, background: T.bdr }} />
        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>try asking</span>
        <div style={{ flex: 1, height: 1, background: T.bdr }} />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 9, justifyContent: "center", maxWidth: 680 }}>
        {suggestions.map((s, i) => (
          <button key={i} className="chip" onClick={() => onPick(s)}>{s}</button>
        ))}
      </div>
    </div>
  );
}

// ── Chat bubbles ──────────────────────────────────────────────────────────────
function Bubble({ msg, statusMsg }) {
  if (msg.role === "user") return (
    <div className="fade-up" style={{ display: "flex", justifyContent: "flex-end" }}>
      <div style={{
        background: `linear-gradient(135deg, #ff4500 0%, #ff6a2f 100%)`,
        color: "#fff", padding: "13px 20px",
        borderRadius: "20px 20px 4px 20px",
        maxWidth: "68%", fontSize: 15, lineHeight: 1.65,
        fontFamily: T.ff, fontWeight: 400,
        boxShadow: "0 5px 20px rgba(255,69,0,.24)",
      }}>
        {msg.content}
        {msg.mode === "deep" && (
          <span style={{ display: "inline-block", marginLeft: 9, background: "rgba(255,255,255,.2)", fontSize: 9, padding: "2px 8px", borderRadius: 10, letterSpacing: 1.5, textTransform: "uppercase", fontFamily: T.mono, verticalAlign: "middle" }}>deep</span>
        )}
      </div>
    </div>
  );

  if (msg.role === "error") return (
    <div className="fade-up" style={{ background: "#fff5f5", border: "1.5px solid #fecaca", color: "#dc2626", padding: "13px 18px", borderRadius: 14, fontSize: 14, fontWeight: 500 }}>
      ⚠ {msg.content}
    </div>
  );

  return (
    <div className="fade-up" style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      <img src="/YAWC_LOGO.png" alt="" style={{ width: 34, height: 34, borderRadius: 9, border: `2px solid ${T.bdr}`, flexShrink: 0, marginTop: 4 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Intent badge */}
        {msg.intent && (() => {
          const im = INTENT_META[msg.intent];
          return im ? (
            <div className="intent-badge" style={{ background: im.bg, color: im.color }}>
              <span>{im.emoji}</span><span>{im.label}</span>
            </div>
          ) : null;
        })()}

        {/* Source pills */}
        {msg.sources?.length > 0 && <SourcePills sources={msg.sources} intent={msg.intent} />}

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
            fontFamily: T.ff, color: T.ink,
            boxShadow: "0 2px 12px rgba(0,0,0,.04)",
          }}>
            <MDText text={msg.content} sources={msg.sources || []} intent={msg.intent} />
            {msg.streaming && <span className="cursor" />}
          </div>
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

// ── Source Pills — platform-aware ─────────────────────────────────────────────
function SourcePills({ sources, intent }) {
  const [expanded, setExpanded] = useState(false);
  const show = expanded ? sources : sources.slice(0, 5);

  // For image intent, render a compact grid of thumbnails instead of pills
  if (intent === "IMAGE") {
    return <ImageSourceGrid sources={sources} expanded={expanded} onToggle={() => setExpanded(o => !o)} />;
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: expanded ? 10 : 0 }}>
        {show.map((s, i) => {
          const pm = getPlatformMeta(s.platform);
          return (
            <a key={i} href={s.url} target="_blank" rel="noreferrer"
               className={`src-pill slide-r ${pm.cls}`}
               style={{ animationDelay: `${i * .05}s` }}>
              <span style={{ fontSize: 11 }}>{pm.icon}</span>
              <span style={{ fontWeight: 700 }}>[{s.index}]</span>
              <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.channel || s.title?.slice(0, 28) || pm.label}
              </span>
              {s.score && s.score !== "0" && (
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
              const pm = getPlatformMeta(s.platform);
              return (
                <a key={i} href={s.url} target="_blank" rel="noreferrer" className="src-card-full">
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                    <span className={`src-pill ${pm.cls}`} style={{ fontSize: 9, padding: "2px 8px", lineHeight: 1.4 }}>
                      {pm.icon} {pm.label}
                    </span>
                    <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut }}>[{s.index}]</span>
                  </div>
                  {/* YouTube: show thumbnail */}
                  {s.platform === "YouTube" && s.thumbnail && (
                    <img src={s.thumbnail} alt={s.title} style={{ width: "100%", height: 90, objectFit: "cover", borderRadius: 6, marginBottom: 6 }} loading="lazy" />
                  )}
                  <div style={{ fontSize: 12, lineHeight: 1.45, marginBottom: 5, color: T.ink, fontWeight: 500 }}>{s.title}</div>
                  {s.channel && <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut }}>{s.channel}</div>}
                  {s.score && s.score !== "0" && <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, marginTop: 2 }}>↑ {s.score}</div>}
                </a>
              );
            })}
          </div>
          <button onClick={() => setExpanded(false)} style={{ marginTop: 8, width: "100%", background: "none", border: `1.5px solid ${T.bdr}`, color: T.mut, padding: "7px", borderRadius: 10, fontSize: 11, cursor: "pointer", fontFamily: T.mono }}>▲ collapse</button>
        </div>
      )}
    </div>
  );
}

// ── Image source grid (special compact view for IMAGE intent) ─────────────────
function ImageSourceGrid({ sources, expanded, onToggle }) {
  const show = expanded ? sources : sources.slice(0, 6);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
        {show.map((s, i) => (
          <a key={i} href={s.url} target="_blank" rel="noreferrer" className="img-grid-item" style={{ animationDelay: `${i * .05}s` }}>
            <img src={s.image_url} alt={s.alt || "image"} loading="lazy" />
            <div style={{ padding: "5px 8px", fontFamily: T.mono, fontSize: 9, color: T.brn, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
              {getPlatformMeta(s.platform).icon} [{s.index}] {s.alt?.slice(0, 24) || s.platform}
            </div>
          </a>
        ))}
      </div>
      {sources.length > 6 && (
        <button onClick={onToggle} style={{ marginTop: 8, width: "100%", background: "none", border: `1.5px solid ${T.bdr}`, color: T.mut, padding: "7px", borderRadius: 10, fontSize: 11, cursor: "pointer", fontFamily: T.mono }}>
          {expanded ? "▲ collapse" : `▼ show all ${sources.length} images`}
        </button>
      )}
    </div>
  );
}

// ── MDText — intent-aware markdown renderer ───────────────────────────────────
//
// Parses the following in LLM output:
//   [YOUTUBE_EMBED: url]   → responsive <iframe> YouTube embed
//   ![alt](url)            → inline image with lightbox-open behaviour
//   ## Heading             → styled section header
//   **bold**               → strong
//   `code`                 → inline code
//   [N]                    → citation badge linked to source
//
function MDText({ text, sources = [], intent }) {
  if (!text) return null;

  const lines = text.split("\n");
  const nodes = [];
  let key = 0;

  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];

    // Empty line → spacer
    if (!line.trim()) {
      nodes.push(<div key={key++} style={{ height: 6 }} />);
      continue;
    }

    // ── YouTube embed tag ── [YOUTUBE_EMBED: url]
    const ytMatch = line.match(/\[YOUTUBE_EMBED:\s*(https?:\/\/[^\]]+)\]/);
    if (ytMatch) {
      const embedUrl = ytMatch[1].trim();
      // The LLM may output description text before/after on the same line — render both
      const before = line.slice(0, ytMatch.index).trim();
      const after  = line.slice(ytMatch.index + ytMatch[0].length).trim();
      nodes.push(
        <div key={key++}>
          {before && <p style={{ margin: "0 0 6px", lineHeight: 1.85 }}>{renderInline(before, sources)}</p>}
          <YouTubeEmbed url={embedUrl} />
          {after  && <p style={{ margin: "6px 0 0", lineHeight: 1.85 }}>{renderInline(after, sources)}</p>}
        </div>
      );
      continue;
    }

    // ── Markdown image ── ![alt](url)
    const imgMatch = line.match(/^!\[([^\]]*)\]\((https?:\/\/[^)]+)\)$/);
    if (imgMatch) {
      const [, alt, url] = imgMatch;
      nodes.push(<InlineImage key={key++} src={url} alt={alt} />);
      continue;
    }

    // ── Section heading ── ## Heading
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

    // ── Paragraph with inline tokens ──
    nodes.push(
      <p key={key++} style={{ margin: "0 0 5px", lineHeight: 1.85 }}>
        {renderInline(line, sources)}
      </p>
    );
  }

  return <div>{nodes}</div>;
}

// ── Inline token renderer (bold, code, cite, text) ────────────────────────────
function renderInline(line, sources) {
  const tokens = tokenise(line);
  return tokens.map((tok, ti) => {
    if (tok.type === "bold") {
      return <strong key={ti} style={{ fontWeight: 700, color: T.ink }}>{tok.text}</strong>;
    }
    if (tok.type === "code") {
      return (
        <code key={ti} style={{ background: "#f4ede8", color: "#c94a00", padding: "1px 6px", borderRadius: 5, fontFamily: T.mono, fontSize: "0.86em" }}>
          {tok.text}
        </code>
      );
    }
    if (tok.type === "cite") {
      const src = sources.find(s => s.index === tok.n);
      return (
        <a key={ti} href={src?.url || "#"} target="_blank" rel="noreferrer"
           className="cite"
           title={src ? `${src.platform || ""} — ${src.title}` : `Source ${tok.n}`}>
          [{tok.n}]
        </a>
      );
    }
    // Inline image within paragraph text: ![alt](url)
    if (tok.type === "img") {
      return <InlineImage key={ti} src={tok.url} alt={tok.alt} compact />;
    }
    return <span key={ti}>{tok.text}</span>;
  });
}

function tokenise(line) {
  const tokens = [];
  // Order matters: check for image ![...](...) before bold/code
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d+)\]|!\[([^\]]*)\]\((https?:\/\/[^)]+)\)/g;
  let last = 0, m;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) tokens.push({ type: "text", text: line.slice(last, m.index) });
    if      (m[1] !== undefined) tokens.push({ type: "bold", text: m[1] });
    else if (m[2] !== undefined) tokens.push({ type: "code", text: m[2] });
    else if (m[3] !== undefined) tokens.push({ type: "cite", n: parseInt(m[3]) });
    else if (m[4] !== undefined) tokens.push({ type: "img",  alt: m[4], url: m[5] });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ type: "text", text: line.slice(last) });
  return tokens;
}

// ── YouTube embed component ───────────────────────────────────────────────────
function YouTubeEmbed({ url }) {
  // Ensure the URL is an embed URL (convert watch URLs if needed)
  let embedUrl = url;
  const watchMatch = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
  if (watchMatch) {
    embedUrl = `https://www.youtube.com/embed/${watchMatch[1]}`;
  }
  // Add privacy-enhanced mode and reasonable defaults
  const finalUrl = embedUrl.includes("?")
    ? embedUrl + "&rel=0&modestbranding=1"
    : embedUrl + "?rel=0&modestbranding=1";

  return (
    <div className="yt-embed-wrap">
      <iframe
        src={finalUrl}
        title="YouTube video"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    </div>
  );
}

// ── Inline image component ────────────────────────────────────────────────────
function InlineImage({ src, alt, compact = false }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;

  if (compact) {
    return (
      <img
        src={src}
        alt={alt}
        onError={() => setFailed(true)}
        style={{ display: "inline-block", maxHeight: 80, maxWidth: 120, objectFit: "cover", borderRadius: 6, margin: "0 4px", verticalAlign: "middle", border: `1px solid ${T.bdr}` }}
        loading="lazy"
      />
    );
  }

  return (
    <a href={src} target="_blank" rel="noreferrer" style={{ display: "block", margin: "10px 0" }}>
      <img
        src={src}
        alt={alt || "image"}
        onError={() => setFailed(true)}
        style={{
          width: "100%", maxHeight: 340, objectFit: "contain",
          borderRadius: 10, border: `1.5px solid ${T.bdr}`,
          background: "#f5ede8", animation: "imgFade .4s ease both",
          cursor: "zoom-in",
        }}
        loading="lazy"
      />
      {alt && (
        <div style={{ fontFamily: T.mono, fontSize: 10, color: T.mut, textAlign: "center", marginTop: 4 }}>
          {alt}
        </div>
      )}
    </a>
  );
}

// ── Input bar ─────────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSend, loading, mode, setMode, textRef, statusMsg }) {
  const onKey = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } };

  return (
    <div style={{ position: "sticky", bottom: 0, zIndex: 40, background: "rgba(255,249,247,.97)", backdropFilter: "blur(18px)", borderTop: `1px solid ${T.bdr}`, padding: "12px 24px 18px" }}>
      {/* Mode row */}
      <div style={{ maxWidth: 860, margin: "0 auto 10px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: 2, textTransform: "uppercase" }}>MODE</span>
        {[
          { id: "quick", icon: "⚡", label: "Quick",         hint: "~15s" },
          { id: "deep",  icon: "🔬", label: "Deep Research", hint: "~60s" },
        ].map(m => (
          <button key={m.id} className={`mode-btn${mode === m.id ? " active" : ""}`} onClick={() => setMode(m.id)} title={m.hint}>
            {m.icon} {m.label}
          </button>
        ))}
        {loading && statusMsg && (
          <span style={{ marginLeft: "auto", fontFamily: T.mono, fontSize: 11, color: T.red, fontStyle: "italic" }}>{statusMsg}</span>
        )}
      </div>

      {/* Input + send */}
      <div style={{ maxWidth: 860, margin: "0 auto", display: "flex", gap: 10, alignItems: "flex-end" }}>
        <textarea
          ref={textRef}
          className="yawc-ta"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder={mode === "deep" ? "Ask a deep question — YAWC classifies intent and scrapes live…" : "Ask anything — text, video, or image queries all work…"}
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
      <div style={{ maxWidth: 860, margin: "7px auto 0", fontFamily: T.mono, fontSize: 9, color: T.mut, letterSpacing: .8, display: "flex", gap: 16 }}>
        <span>↵ Enter to search</span>
        <span>Shift+↵ newline</span>
        <span>🧠 Auto-detects: text · video · image</span>
      </div>
    </div>
  );
}
