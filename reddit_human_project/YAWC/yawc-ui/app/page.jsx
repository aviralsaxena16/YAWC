// YAWC v3 — Yet Another Web Crawler
// app/page.jsx  (Next.js App Router)
// NEXT_PUBLIC_API_URL=http://localhost:8000
// Place your logo at:  public/logo.png

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

    @keyframes spin   { to { transform: rotate(360deg); } }
    @keyframes fadeUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
    @keyframes slideR { from { opacity:0; transform:translateX(-8px); } to { opacity:1; transform:translateX(0); } }
    @keyframes blink  { 0%,100%{opacity:1} 50%{opacity:0} }
    @keyframes dotpop { 0%,100%{transform:scaleY(.35);opacity:.25} 50%{transform:scaleY(1);opacity:1} }
    @keyframes stripe { 0%{background-position:-400px 0} 100%{background-position:400px 0} }

    .fade-up { animation: fadeUp .38s cubic-bezier(.22,.68,0,1.15) both; }
    .slide-r { animation: slideR .28s ease both; }

    .chip {
      background: #fff;
      border: 1.5px solid #e5d8d0;
      color: #5a3d2b;
      border-radius: 100px;
      padding: 9px 18px;
      font-size: 13px;
      font-family: 'Bricolage Grotesque', sans-serif;
      font-weight: 400;
      cursor: pointer;
      transition: all .17s ease;
      white-space: nowrap;
      line-height: 1;
    }
    .chip:hover {
      background: #ff4500;
      border-color: #ff4500;
      color: #fff;
      transform: translateY(-2px);
      box-shadow: 0 5px 16px rgba(255,69,0,.28);
    }

    .src-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: #fff8f5;
      border: 1.5px solid #ffd8c8;
      border-radius: 8px;
      padding: 4px 10px;
      text-decoration: none;
      color: #5a3d2b;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      transition: all .15s;
    }
    .src-pill:hover { background: #ff4500; border-color: #ff4500; color: #fff; transform: translateY(-1px); }

    .src-card-full {
      display: block;
      background: #fff;
      border: 1.5px solid #ede0d8;
      border-radius: 12px;
      padding: 12px 16px;
      text-decoration: none;
      color: #1a1008;
      transition: all .17s;
    }
    .src-card-full:hover { border-color: #ff4500; box-shadow: 0 4px 18px rgba(255,69,0,.11); transform: translateY(-2px); }

    .mode-btn {
      border-radius: 100px;
      padding: 7px 18px;
      font-size: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 500;
      cursor: pointer;
      transition: all .17s;
      border: 1.5px solid #e5d8d0;
      background: #fff;
      color: #8a6a58;
      letter-spacing: .5px;
      line-height: 1;
    }
    .mode-btn.active { background: #ff4500; border-color: #ff4500; color: #fff; box-shadow: 0 2px 10px rgba(255,69,0,.28); }
    .mode-btn:not(.active):hover { border-color: #ff4500; color: #ff4500; }

    .send-btn { border-radius: 14px; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 50px; height: 50px; transition: all .17s; }
    .send-btn:hover:not(:disabled) { transform: scale(1.05); box-shadow: 0 5px 18px rgba(255,69,0,.38); }

    .yawc-ta {
      flex: 1;
      background: #fff;
      border: 1.5px solid #e5d8d0;
      border-radius: 16px;
      padding: 14px 18px;
      color: #1a1008;
      font-family: 'Bricolage Grotesque', sans-serif;
      font-size: 15px;
      line-height: 1.5;
      resize: none;
      outline: none;
      min-height: 50px;
      max-height: 140px;
      transition: border-color .2s, box-shadow .2s;
    }
    .yawc-ta:focus { border-color: #ff4500; box-shadow: 0 0 0 3px rgba(255,69,0,.1); }
    .yawc-ta::placeholder { color: #c4a898; }
    .yawc-ta:disabled { opacity:.55; cursor:not-allowed; }

    .cite {
      display: inline-block;
      background: #fff0e8;
      color: #ff4500;
      padding: 0 5px;
      border-radius: 5px;
      font-size: .78em;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      text-decoration: none;
      margin: 0 1px;
      transition: all .13s;
      vertical-align: middle;
    }
    .cite:hover { background: #ff4500; color: #fff; }

    .cursor { display:inline-block; width:2px; height:1em; background:#ff4500; vertical-align:text-bottom; animation:blink .75s step-end infinite; margin-left:2px; }
    .dot { display:inline-block; width:5px; height:20px; background:#ff4500; border-radius:3px; margin:0 2px; animation:dotpop 1s ease infinite; }
  `;
  document.head.appendChild(s);
}

// ── Tokens ────────────────────────────────────────────────────────────────────
const T = {
  bg:    "#fff9f7",
  white: "#ffffff",
  bdr:   "#ede0d8",
  red:   "#ff4500",
  rdim:  "#fff0e8",
  org:   "#ff6a2f",
  ink:   "#1a1008",
  brn:   "#5a3d2b",
  mut:   "#b8a099",
  ff:    "'Bricolage Grotesque', sans-serif",
  mono:  "'JetBrains Mono', monospace",
  head:  "'Bebas Neue', sans-serif",
};

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

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [messages, statusMsg]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput(""); setLoading(true); setStatusMsg("");
    setMessages(p => [...p, { role:"user", content:q, mode }]);

    const aid = Date.now();
    setMessages(p => [...p, { role:"assistant", content:"", sources:[], streaming:true, id:aid }]);

    if (esRef.current) esRef.current.close();
    const es = new EventSource(`${API}/api/search?q=${encodeURIComponent(q)}&mode=${mode}`);
    esRef.current = es;

    es.addEventListener("status",  e => setStatusMsg(JSON.parse(e.data).message));
    es.addEventListener("sources", e => {
      const { sources } = JSON.parse(e.data);
      setMessages(p => p.map(m => m.id === aid ? { ...m, sources } : m));
    });
    es.addEventListener("token", e => {
      const { token } = JSON.parse(e.data);
      setStatusMsg("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: m.content + token } : m));
    });
    es.addEventListener("done", () => {
      setMessages(p => p.map(m => m.id === aid ? { ...m, streaming:false } : m));
      setLoading(false); setStatusMsg(""); es.close();
    });
    es.addEventListener("error", e => {
      let msg = "Something went wrong.";
      try { msg = JSON.parse(e.data).message; } catch (_) {}
      setMessages(p => p.filter(m => m.id !== aid).concat([{ role:"error", content:msg }]));
      setLoading(false); setStatusMsg(""); es.close();
    });
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return;
      setMessages(p => p.filter(m => m.id !== aid).concat([{ role:"error", content:"Connection lost — is the backend running on port 8000?" }]));
      setLoading(false); setStatusMsg(""); es.close();
    };
  }, [input, loading, mode]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div style={{ display:"flex", flexDirection:"column", minHeight:"100vh", background:T.bg }}>
      {/* Animated accent stripe at top */}
      <div style={{ height:3, background:"linear-gradient(90deg,#ff4500,#ff9a3c,#ff6a2f,#ff4500)", backgroundSize:"300% 100%", animation:"stripe 4s linear infinite" }} />

      <TopBar />

      <main style={{ flex:1, display:"flex", flexDirection:"column" }}>
        {isEmpty
          ? <Hero onPick={s => { setInput(s); textRef.current?.focus(); }} />
          : (
            <div style={{ flex:1, maxWidth:860, width:"100%", margin:"0 auto", padding:"36px 24px 0", display:"flex", flexDirection:"column", gap:28 }}>
              {messages.map((m, i) => <Bubble key={m.id || i} msg={m} statusMsg={statusMsg} />)}
              {loading && statusMsg && !messages.some(m => m.streaming && m.content) && <ThinkingBubble msg={statusMsg} />}
              <div ref={bottomRef} style={{ height:24 }} />
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
    <nav style={{ background:T.white, borderBottom:`1px solid ${T.bdr}`, position:"sticky", top:0, zIndex:50 }}>
      <div style={{ maxWidth:1100, margin:"0 auto", padding:"0 28px", height:58, display:"flex", alignItems:"center", justifyContent:"space-between" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          <img src="/YAWC_LOGO.png" alt="YAWC" style={{ width:32, height:32, borderRadius:7 }} />
          <span style={{ fontFamily:T.head, fontSize:27, letterSpacing:2, color:T.ink, lineHeight:1 }}>YAWC</span>
          <div style={{ width:1, height:16, background:T.bdr, margin:"0 6px" }} />
          <span style={{ fontFamily:T.mono, fontSize:9, color:T.mut, letterSpacing:2, textTransform:"uppercase" }}>Yet Another Web Crawler</span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:7, background:T.rdim, borderRadius:100, padding:"5px 14px" }}>
          <div style={{ width:6, height:6, borderRadius:"50%", background:"#16a34a", boxShadow:"0 0 7px #16a34a" }} />
          <span style={{ fontFamily:T.mono, fontSize:9, color:T.brn, letterSpacing:1.5, textTransform:"uppercase" }}>live search</span>
        </div>
      </div>
    </nav>
  );
}

// ── Hero empty state ──────────────────────────────────────────────────────────
function Hero({ onPick }) {
  const suggestions = [
    "Best mechanical keyboard under $150?",
    "Rust vs Go — which should I learn?",
    "How to deal with developer burnout?",
    "Best budget GPU for gaming 2025?",
    "MacBook Pro vs Dell XPS for dev?",
    "Is learning Vim worth it in 2025?",
    "Top espresso machines for home use?",
    "Best Python web framework for beginners?",
  ];

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", padding:"52px 24px 150px", textAlign:"center" }}>

      {/* Logo with glow */}
      <div style={{ position:"relative", marginBottom:28 }}>
        <div style={{ position:"absolute", inset:-18, borderRadius:"50%", background:"radial-gradient(circle, rgba(255,69,0,.16) 0%, transparent 68%)", filter:"blur(10px)" }} />
        <img src="/YAWC_LOGO.png" alt="YAWC" style={{
          width:96, height:96, borderRadius:22,
          position:"relative", zIndex:1,
          boxShadow:"0 18px 52px rgba(255,69,0,.24), 0 4px 14px rgba(0,0,0,.07)",
        }} />
      </div>

      {/* Big headline */}
      <h1 style={{
        fontFamily: T.head,
        fontSize: "clamp(58px, 10vw, 100px)",
        letterSpacing: 5,
        lineHeight: 0.93,
        color: T.ink,
        textTransform: "uppercase",
        marginBottom: 20,
      }}>
        Yet Another<br />
        <span style={{ color:T.red, WebkitTextStroke:"0px" }}>Web Crawler</span>
      </h1>

      {/* Red pill badge */}
      <div style={{
        display:"inline-flex", alignItems:"center", gap:8,
        background:T.red, color:"#fff",
        borderRadius:100, padding:"8px 22px",
        fontFamily:T.mono, fontSize:11, letterSpacing:2,
        textTransform:"uppercase", marginBottom:22,
        boxShadow:"0 5px 20px rgba(255,69,0,.32)",
      }}>
        🕷️ &nbsp;YAWC · Real Reddit Research
      </div>

      {/* Description */}
      <p style={{ fontSize:15, color:T.brn, lineHeight:1.85, maxWidth:460, marginBottom:42, fontWeight:400 }}>
        Spins up a headless browser, scrapes Reddit live, and synthesizes a
        research&#8209;grade answer with inline citations.{" "}
        <strong style={{ color:T.ink, fontWeight:700 }}>No hallucinations. No paywalls. Just Reddit.</strong>
      </p>

      {/* Divider */}
      <div style={{ display:"flex", alignItems:"center", gap:14, width:"100%", maxWidth:560, marginBottom:22 }}>
        <div style={{ flex:1, height:1, background:T.bdr }} />
        <span style={{ fontFamily:T.mono, fontSize:10, color:T.mut, letterSpacing:2, textTransform:"uppercase" }}>try asking</span>
        <div style={{ flex:1, height:1, background:T.bdr }} />
      </div>

      {/* Chips */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:9, justifyContent:"center", maxWidth:680 }}>
        {suggestions.map((s, i) => (
          <button key={i} className="chip" onClick={() => onPick(s)}>{s}</button>
        ))}
      </div>
    </div>
  );
}

// ── Bubbles ───────────────────────────────────────────────────────────────────
function Bubble({ msg, statusMsg }) {
  if (msg.role === "user") return (
    <div className="fade-up" style={{ display:"flex", justifyContent:"flex-end" }}>
      <div style={{
        background:`linear-gradient(135deg, #ff4500 0%, #ff6a2f 100%)`,
        color:"#fff",
        padding:"13px 20px",
        borderRadius:"20px 20px 4px 20px",
        maxWidth:"68%", fontSize:15, lineHeight:1.65,
        fontFamily:T.ff, fontWeight:400,
        boxShadow:"0 5px 20px rgba(255,69,0,.24)",
      }}>
        {msg.content}
        {msg.mode === "deep" && (
          <span style={{ display:"inline-block", marginLeft:9, background:"rgba(255,255,255,.2)", fontSize:9, padding:"2px 8px", borderRadius:10, letterSpacing:1.5, textTransform:"uppercase", fontFamily:T.mono, verticalAlign:"middle" }}>deep</span>
        )}
      </div>
    </div>
  );

  if (msg.role === "error") return (
    <div className="fade-up" style={{ background:"#fff5f5", border:"1.5px solid #fecaca", color:"#dc2626", padding:"13px 18px", borderRadius:14, fontSize:14, fontWeight:500 }}>
      ⚠ {msg.content}
    </div>
  );

  return (
    <div className="fade-up" style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
      <img src="/YAWC_LOGO.png" alt="" style={{ width:34, height:34, borderRadius:9, border:`2px solid ${T.bdr}`, flexShrink:0, marginTop:4 }} />
      <div style={{ flex:1, minWidth:0 }}>
        {msg.sources?.length > 0 && <SourcePills sources={msg.sources} />}
        {msg.streaming && statusMsg && !msg.content && (
          <div style={{ fontFamily:T.mono, fontSize:12, color:T.mut, fontStyle:"italic", marginBottom:10 }}>{statusMsg}</div>
        )}
        {(msg.content || msg.streaming) && (
          <div style={{
            background:T.white, border:`1.5px solid ${T.bdr}`,
            borderRadius:"4px 18px 18px 18px",
            padding:"18px 22px", fontSize:15, lineHeight:1.85,
            fontFamily:T.ff, color:T.ink,
            boxShadow:"0 2px 12px rgba(0,0,0,.04)",
          }}>
            <MDText text={msg.content} sources={msg.sources || []} />
            {msg.streaming && <span className="cursor" />}
          </div>
        )}
      </div>
    </div>
  );
}

function ThinkingBubble({ msg }) {
  return (
    <div className="fade-up" style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
      <img src="/YAWC_LOGO.png" alt="" style={{ width:34, height:34, borderRadius:9, border:`2px solid ${T.bdr}`, opacity:.55, flexShrink:0, marginTop:4 }} />
      <div style={{ background:T.white, border:`1.5px solid ${T.bdr}`, borderRadius:"4px 18px 18px 18px", padding:"16px 20px", display:"flex", alignItems:"center", gap:8 }}>
        <span className="dot" style={{ animationDelay:"0s" }} />
        <span className="dot" style={{ animationDelay:".14s" }} />
        <span className="dot" style={{ animationDelay:".28s" }} />
        <span style={{ fontFamily:T.mono, fontSize:12, color:T.red, fontStyle:"italic", marginLeft:8 }}>{msg}</span>
      </div>
    </div>
  );
}

// ── Source pills ──────────────────────────────────────────────────────────────
function SourcePills({ sources }) {
  const [expanded, setExpanded] = useState(false);
  const show = expanded ? sources : sources.slice(0, 4);

  return (
    <div style={{ marginBottom:10 }}>
      <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom: expanded ? 10 : 0 }}>
        {show.map((s, i) => (
          <a key={i} href={s.url} target="_blank" rel="noreferrer" className="src-pill slide-r" style={{ animationDelay:`${i*.05}s` }}>
            <span style={{ color:T.red, fontWeight:700 }}>[{s.index}]</span>
            <span style={{ maxWidth:130, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.subreddit || "reddit"}</span>
            <span style={{ color:T.mut }}>↑{s.score}</span>
          </a>
        ))}
        {!expanded && sources.length > 4 && (
          <button onClick={() => setExpanded(true)} style={{ background:"none", border:`1.5px solid ${T.bdr}`, color:T.mut, borderRadius:8, padding:"4px 10px", fontSize:11, cursor:"pointer", fontFamily:T.mono }}>
            +{sources.length - 4} more ↓
          </button>
        )}
      </div>
      {expanded && (
        <div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
            {sources.map((s, i) => (
              <a key={i} href={s.url} target="_blank" rel="noreferrer" className="src-card-full">
                <div style={{ fontFamily:T.mono, fontSize:9, color:T.red, letterSpacing:1.5, marginBottom:4, textTransform:"uppercase" }}>[{s.index}] {s.subreddit || "reddit"}</div>
                <div style={{ fontSize:12, lineHeight:1.45, marginBottom:5, color:T.ink, fontWeight:500 }}>{s.title}</div>
                <div style={{ fontFamily:T.mono, fontSize:10, color:T.mut }}>↑ {s.score}</div>
              </a>
            ))}
          </div>
          <button onClick={() => setExpanded(false)} style={{ marginTop:8, width:"100%", background:"none", border:`1.5px solid ${T.bdr}`, color:T.mut, padding:"7px", borderRadius:10, fontSize:11, cursor:"pointer", fontFamily:T.mono }}>▲ collapse</button>
        </div>
      )}
    </div>
  );
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function MDText({ text, sources = [] }) {
  if (!text) return null;
  return (
    <div>
      {text.split("\n").map((line, li) => {
        if (!line.trim()) return <div key={li} style={{ height:6 }} />;
        if (line.startsWith("## ")) return (
          <div key={li} style={{ marginTop:20, marginBottom:8 }}>
            <span style={{ fontFamily:T.head, fontSize:20, letterSpacing:1.5, color:T.ink, textTransform:"uppercase", borderBottom:`2.5px solid ${T.red}`, paddingBottom:3 }}>
              {line.slice(3)}
            </span>
          </div>
        );
        return (
          <p key={li} style={{ margin:"0 0 5px", lineHeight:1.85 }}>
            {tokenise(line).map((tok, ti) => {
              if (tok.type === "bold") return <strong key={ti} style={{ fontWeight:700, color:T.ink }}>{tok.text}</strong>;
              if (tok.type === "code") return <code key={ti} style={{ background:"#f4ede8", color:"#c94a00", padding:"1px 6px", borderRadius:5, fontFamily:T.mono, fontSize:"0.86em" }}>{tok.text}</code>;
              if (tok.type === "cite") {
                const src = sources.find(s => s.index === tok.n);
                return <a key={ti} href={src?.url || "#"} target="_blank" rel="noreferrer" className="cite" title={src ? `${src.subreddit} — ${src.title}` : `Source ${tok.n}`}>[{tok.n}]</a>;
              }
              return <span key={ti}>{tok.text}</span>;
            })}
          </p>
        );
      })}
    </div>
  );
}

function tokenise(line) {
  const tokens = [], re = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d+)\]/g;
  let last = 0, m;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) tokens.push({ type:"text", text:line.slice(last, m.index) });
    if      (m[1] !== undefined) tokens.push({ type:"bold", text:m[1] });
    else if (m[2] !== undefined) tokens.push({ type:"code", text:m[2] });
    else if (m[3] !== undefined) tokens.push({ type:"cite", n:parseInt(m[3]) });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ type:"text", text:line.slice(last) });
  return tokens;
}

// ── Input bar ─────────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSend, loading, mode, setMode, textRef, statusMsg }) {
  const onKey = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } };

  return (
    <div style={{ position:"sticky", bottom:0, zIndex:40, background:"rgba(255,249,247,.97)", backdropFilter:"blur(18px)", borderTop:`1px solid ${T.bdr}`, padding:"12px 24px 18px" }}>

      {/* Mode row */}
      <div style={{ maxWidth:860, margin:"0 auto 10px", display:"flex", alignItems:"center", gap:8, flexWrap:"wrap" }}>
        <span style={{ fontFamily:T.mono, fontSize:9, color:T.mut, letterSpacing:2, textTransform:"uppercase" }}>MODE</span>
        {[
          { id:"quick", icon:"⚡", label:"Quick",         hint:"8 posts · ~15s" },
          { id:"deep",  icon:"🔬", label:"Deep Research", hint:"30 posts · ~60s" },
        ].map(m => (
          <button key={m.id} className={`mode-btn${mode === m.id ? " active" : ""}`} onClick={() => setMode(m.id)} title={m.hint}>
            {m.icon} {m.label}
          </button>
        ))}
        {loading && statusMsg && (
          <span style={{ marginLeft:"auto", fontFamily:T.mono, fontSize:11, color:T.red, fontStyle:"italic" }}>{statusMsg}</span>
        )}
      </div>

      {/* Input + send */}
      <div style={{ maxWidth:860, margin:"0 auto", display:"flex", gap:10, alignItems:"flex-end" }}>
        <textarea
          ref={textRef}
          className="yawc-ta"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder={mode === "deep" ? "Ask a deep question — YAWC scrapes 30 posts…" : "Ask anything — YAWC searches Reddit live…"}
          disabled={loading}
          rows={1}
        />
        <button className="send-btn" onClick={onSend} disabled={loading || !value.trim()}
          style={{ background: loading || !value.trim() ? "#e8ddd8" : "linear-gradient(135deg,#ff4500,#ff6a2f)" }}>
          {loading
            ? <div style={{ width:18, height:18, border:"2.5px solid rgba(255,255,255,.35)", borderTopColor:"#fff", borderRadius:"50%", animation:"spin .65s linear infinite" }} />
            : <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke={loading || !value.trim() ? "#b8a099" : "#fff"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
          }
        </button>
      </div>

      {/* Hints */}
      <div style={{ maxWidth:860, margin:"7px auto 0", fontFamily:T.mono, fontSize:9, color:T.mut, letterSpacing:.8, display:"flex", gap:16 }}>
        <span>↵ Enter to search</span>
        <span>Shift+↵ newline</span>
        <span>{mode === "quick" ? "⚡ ~8 posts" : "🔬 ~30 posts · themes + pros/cons"}</span>
      </div>
    </div>
  );
}
