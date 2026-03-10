// YAWC v2 — Yet Another Web Crawler
// app/page.jsx  (Next.js App Router)
// NEXT_PUBLIC_API_URL=http://localhost:8000

"use client";
import { useState, useRef, useEffect, useCallback } from "react";

// ── Logo ──────────────────────────────────────────────────────────────────────
const LOGO = "/YAWC_LOGO.png";
const API  = (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) || "http://localhost:8000";

// ── Global styles ─────────────────────────────────────────────────────────────
if (typeof document !== "undefined" && !document.getElementById("yawc-v2-styles")) {
  const s = document.createElement("style");
  s.id = "yawc-v2-styles";
  s.textContent = `
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:ital,wght@0,400;0,500;1,400&display=swap');
    *, *::before, *::after { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { margin: 0; background: #fafafa; color: #111; font-family: 'JetBrains Mono', monospace; }

    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: #f0f0f0; }
    ::-webkit-scrollbar-thumb { background: #e63000; border-radius: 2px; }

    @keyframes spin     { to { transform: rotate(360deg); } }
    @keyframes pulse    { 0%,100% { opacity:.2; transform:scale(.6); } 50% { opacity:1; transform:scale(1); } }
    @keyframes fadein   { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
    @keyframes slidein  { from { opacity:0; transform:translateX(-8px); } to { opacity:1; transform:translateX(0); } }
    @keyframes blink    { 0%,100% { opacity:1; } 50% { opacity:0; } }
    @keyframes shimmer  { 0% { background-position:-200% 0; } 100% { background-position:200% 0; } }

    .msg-in  { animation: fadein .35s cubic-bezier(.22,.68,0,1.2) both; }
    .src-in  { animation: slidein .3s ease both; }

    .sugg:hover  { background:#e63000!important; color:#fff!important; border-color:#e63000!important; }
    .src-card:hover { transform:translateY(-2px); box-shadow:0 6px 20px rgba(230,48,0,.12)!important; }
    .mode-btn.active { background:#e63000!important; color:#fff!important; border-color:#e63000!important; }
    .mode-btn:not(.active):hover { border-color:#e63000!important; color:#e63000!important; }

    textarea:focus { border-color:#e63000!important; box-shadow:0 0 0 3px rgba(230,48,0,.1)!important; }
    .send-btn:hover:not(:disabled) { background:#c22800!important; transform:scale(1.04); }
    .cite-tag { cursor:pointer; }
    .cite-tag:hover { background:#e63000!important; color:#fff!important; }

    .cursor-blink { display:inline-block; width:2px; height:1em; background:#e63000;
                    vertical-align:text-bottom; animation:blink .8s step-end infinite; margin-left:1px; }
  `;
  document.head.appendChild(s);
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  bg:      "#fafafa",
  surface: "#ffffff",
  border:  "#e8e8e8",
  red:     "#e63000",
  redDim:  "#fff0ec",
  text:    "#111111",
  sub:     "#555555",
  muted:   "#999999",
  ff:      "'JetBrains Mono', monospace",
  fh:      "'Syne', sans-serif",
};

// ── Main App ──────────────────────────────────────────────────────────────────
export default function YAWCApp() {
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [mode,      setMode]      = useState("quick");   // "quick" | "deep"
  const [loading,   setLoading]   = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  // sources arrive before LLM finishes — store separately
  const [pendingSources, setPendingSources] = useState([]);
  const bottomRef = useRef(null);
  const textRef   = useRef(null);
  const esRef     = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMsg]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || loading) return;

    setInput("");
    setLoading(true);
    setStatusMsg("");
    setPendingSources([]);

    setMessages(prev => [...prev, { role: "user", content: q, mode }]);

    if (esRef.current) esRef.current.close();

    // Placeholder assistant message — we'll fill it via token streaming
    const assistantIdx = Date.now();
    setMessages(prev => [
      ...prev,
      { role: "assistant", content: "", sources: [], streaming: true, id: assistantIdx },
    ]);

    const url = `${API}/api/search?q=${encodeURIComponent(q)}&mode=${mode}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("status", e => {
      setStatusMsg(JSON.parse(e.data).message);
    });

    // ★ Sources arrive BEFORE LLM finishes — show them instantly
    es.addEventListener("sources", e => {
      const { sources } = JSON.parse(e.data);
      setPendingSources(sources);
      // Attach to the streaming assistant message
      setMessages(prev => prev.map(m =>
        m.id === assistantIdx ? { ...m, sources } : m
      ));
    });

    // ★ Token streaming — append each chunk to the assistant bubble
    es.addEventListener("token", e => {
      const { token } = JSON.parse(e.data);
      setStatusMsg("");
      setMessages(prev => prev.map(m =>
        m.id === assistantIdx ? { ...m, content: m.content + token } : m
      ));
    });

    es.addEventListener("done", () => {
      setMessages(prev => prev.map(m =>
        m.id === assistantIdx ? { ...m, streaming: false } : m
      ));
      setLoading(false);
      setPendingSources([]);
      es.close();
    });

    es.addEventListener("error", e => {
      let msg = "Something went wrong.";
      try { msg = JSON.parse(e.data).message; } catch(_) {}
      setMessages(prev => prev
        .filter(m => m.id !== assistantIdx)
        .concat([{ role: "error", content: msg }])
      );
      setLoading(false);
      setStatusMsg("");
      es.close();
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return;
      setMessages(prev => prev
        .filter(m => m.id !== assistantIdx)
        .concat([{ role: "error", content: "Connection lost — is the backend running on port 8000?" }])
      );
      setLoading(false);
      setStatusMsg("");
      es.close();
    };
  }, [input, loading, mode]);

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div style={{ display:"flex", flexDirection:"column", minHeight:"100vh",
                  background:T.bg, fontFamily:T.ff, color:T.text }}>
      <Header />
      <main style={{ flex:1, display:"flex", flexDirection:"column" }}>
        {isEmpty
          ? <EmptyState onPick={s => { setInput(s); textRef.current?.focus(); }} />
          : (
            <div style={{ flex:1, maxWidth:860, width:"100%", margin:"0 auto",
                          padding:"32px 24px 0", display:"flex",
                          flexDirection:"column", gap:32 }}>
              {messages.map((m, i) => <MessageBubble key={m.id || i} msg={m} statusMsg={statusMsg} />)}
              {loading && statusMsg && !messages.some(m => m.streaming) && (
                <StatusBubble msg={statusMsg} />
              )}
              <div ref={bottomRef} style={{ height:20 }} />
            </div>
          )
        }
      </main>
      <InputBar
        value={input}
        onChange={setInput}
        onSend={send}
        loading={loading}
        mode={mode}
        setMode={setMode}
        textRef={textRef}
        statusMsg={statusMsg}
      />
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────────────────
function Header() {
  return (
    <header style={{
      background: T.surface,
      borderBottom: `1px solid ${T.border}`,
      position: "sticky", top:0, zIndex:50,
    }}>
      <div style={{ maxWidth:860, margin:"0 auto", padding:"12px 24px",
                    display:"flex", alignItems:"center", gap:14 }}>
        <img src={LOGO} alt="YAWC" style={{ width:42, height:42, borderRadius:10, flexShrink:0 }} />
        <div>
          <div style={{ fontFamily:T.fh, fontSize:20, fontWeight:800,
                        letterSpacing:1, color:T.text, lineHeight:1 }}>YAWC</div>
          <div style={{ fontSize:9, color:T.muted, letterSpacing:2,
                        textTransform:"uppercase", marginTop:2 }}>
            Yet Another Web Crawler
          </div>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:8 }}>
          <div style={{ width:7, height:7, borderRadius:"50%",
                        background:"#16a34a", boxShadow:"0 0 8px #16a34a66" }} />
          <span style={{ fontSize:10, color:T.muted, letterSpacing:1,
                         textTransform:"uppercase" }}>live reddit search</span>
        </div>
      </div>
    </header>
  );
}

// ── Empty / Hero state ─────────────────────────────────────────────────────────
function EmptyState({ onPick }) {
  const suggestions = [
    "Best mechanical keyboard under $150?",
    "Rust vs Go — which should I learn?",
    "How to deal with developer burnout?",
    "Best budget GPU for gaming 2025?",
    "Is learning Vim worth it in 2025?",
    "Top espresso machines for home use?",
    "MacBook Pro vs Dell XPS for dev?",
    "Best Python web framework for beginners?",
  ];

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column",
                  alignItems:"center", justifyContent:"center",
                  padding:"48px 24px 120px" }}>
      {/* Hero */}
      <div style={{ textAlign:"center", maxWidth:600, marginBottom:40 }}>
        <img src={LOGO} alt="" style={{ width:88, height:88, borderRadius:20,
                                        marginBottom:24, boxShadow:"0 12px 40px rgba(230,48,0,.2)" }} />
        <h1 style={{ fontFamily:T.fh, fontSize:40, fontWeight:800,
                     margin:"0 0 8px", letterSpacing:-1, color:T.text, lineHeight:1.1 }}>
          Yet Another Web Crawler
        </h1>
        <div style={{ display:"inline-block", background:T.red, color:"#fff",
                      fontFamily:T.ff, fontSize:11, letterSpacing:3,
                      padding:"4px 14px", borderRadius:20, marginBottom:16,
                      textTransform:"uppercase" }}>
          YAWC · Real Reddit Research
        </div>
        <p style={{ fontSize:13, color:T.sub, lineHeight:1.9,
                    margin:"12px auto 0", maxWidth:460 }}>
          Spins up a headless browser, scrapes Reddit live,
          and synthesizes a research-grade answer with inline citations.
          No hallucinations. No paywalls. Just Reddit.
        </p>
      </div>

      {/* Suggestion chips */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:8,
                    justifyContent:"center", maxWidth:640 }}>
        {suggestions.map((s, i) => (
          <button key={i} className="sugg" onClick={() => onPick(s)} style={{
            background: T.surface,
            border: `1px solid ${T.border}`,
            color: T.sub,
            borderRadius: 20, padding: "8px 16px",
            fontSize: 12, cursor: "pointer",
            transition: "all .18s",
            fontFamily: T.ff,
          }}>{s}</button>
        ))}
      </div>
    </div>
  );
}

// ── Message Bubble ─────────────────────────────────────────────────────────────
function MessageBubble({ msg, statusMsg = "" }) {
  if (msg.role === "user") return (
    <div className="msg-in" style={{ display:"flex", justifyContent:"flex-end" }}>
      <div style={{
        background: T.red, color:"#fff",
        padding: "12px 18px", borderRadius:"18px 18px 4px 18px",
        maxWidth:"70%", fontSize:14, lineHeight:1.7,
        fontFamily: T.ff,
      }}>
        {msg.content}
        {msg.mode === "deep" && (
          <span style={{ display:"inline-block", marginLeft:8,
                         background:"rgba(255,255,255,.2)", fontSize:9,
                         padding:"2px 7px", borderRadius:10, letterSpacing:1,
                         textTransform:"uppercase" }}>deep</span>
        )}
      </div>
    </div>
  );

  if (msg.role === "error") return (
    <div className="msg-in" style={{
      background:"#fff5f5", border:"1px solid #fecaca",
      color:"#dc2626", padding:"12px 16px", borderRadius:10, fontSize:13,
    }}>⚠ {msg.content}</div>
  );

  // Assistant
  return (
    <div className="msg-in" style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
      <img src={LOGO} alt="" style={{ width:32, height:32, borderRadius:8,
                                       flexShrink:0, marginTop:4 }} />
      <div style={{ flex:1, minWidth:0 }}>
        {/* Sources pill row — shown early, before LLM finishes */}
        {msg.sources?.length > 0 && (
          <SourcePills sources={msg.sources} />
        )}
        {/* Answer bubble */}
        <div style={{
          background: T.surface,
          border: `1px solid ${T.border}`,
          padding: "16px 20px",
          borderRadius: "4px 18px 18px 18px",
          fontSize: 14, lineHeight: 1.8,
        }}>
          {msg.streaming && statusMsg && (
            <div style={{ color:T.muted, fontSize:12, fontStyle:"italic", marginBottom:8 }}>
              {statusMsg}
            </div>
          )}
          <MDText text={msg.content} sources={msg.sources || []} />
          {msg.streaming && <span className="cursor-blink" />}
        </div>
      </div>
    </div>
  );
}

// ── Source Pills (shown inline, before LLM done) ──────────────────────────────
function SourcePills({ sources }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{ marginBottom:10 }}>
      {/* Compact pill bar */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom: expanded ? 10 : 0 }}>
        {sources.slice(0, expanded ? sources.length : 5).map((s, i) => (
          <a key={i} href={s.url} target="_blank" rel="noreferrer"
             className="src-card src-in"
             style={{
               display:"inline-flex", alignItems:"center", gap:5,
               background: T.surface,
               border:`1px solid ${T.border}`,
               borderRadius:6, padding:"4px 10px",
               textDecoration:"none", color:T.sub,
               fontSize:11, transition:"all .18s",
               animationDelay: `${i*0.04}s`,
             }}>
            <span style={{ color:T.red, fontWeight:700 }}>[{s.index}]</span>
            <span style={{ maxWidth:160, overflow:"hidden",
                           textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
              {s.subreddit || "reddit"}
            </span>
            <span style={{ color:T.muted }}>↑{s.score}</span>
          </a>
        ))}
        {!expanded && sources.length > 5 && (
          <button onClick={() => setExpanded(true)} style={{
            background:"none", border:`1px solid ${T.border}`,
            color:T.muted, borderRadius:6, padding:"4px 10px",
            fontSize:11, cursor:"pointer",
          }}>+{sources.length - 5} more</button>
        )}
      </div>

      {/* Expanded full source cards */}
      {expanded && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
          {sources.map((s, i) => (
            <a key={i} href={s.url} target="_blank" rel="noreferrer"
               className="src-card"
               style={{
                 background:T.surface, border:`1px solid ${T.border}`,
                 borderRadius:10, padding:"10px 14px",
                 textDecoration:"none", color:T.text,
                 transition:"all .18s",
               }}>
              <div style={{ fontSize:9, color:T.red, letterSpacing:1.5,
                            marginBottom:3, textTransform:"uppercase" }}>
                [{s.index}] {s.subreddit || "reddit"}
              </div>
              <div style={{ fontSize:12, lineHeight:1.45,
                            marginBottom:4, color:T.text }}>{s.title}</div>
              <div style={{ fontSize:10, color:T.muted }}>↑ {s.score}</div>
            </a>
          ))}
          <button onClick={() => setExpanded(false)} style={{
            gridColumn:"1/-1", background:"none",
            border:`1px solid ${T.border}`, color:T.muted,
            padding:"6px", borderRadius:8, fontSize:11, cursor:"pointer",
          }}>▲ collapse</button>
        </div>
      )}
    </div>
  );
}

// ── Status bubble ─────────────────────────────────────────────────────────────
function StatusBubble({ msg }) {
  const dot = (d) => ({
    width:7, height:7, borderRadius:"50%", background:T.red,
    display:"inline-block", margin:"0 2px",
    animation:`pulse 1.3s ease ${d}s infinite`,
  });
  return (
    <div style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
      <img src={LOGO} alt="" style={{ width:32, height:32, borderRadius:8,
                                       flexShrink:0, opacity:.5 }} />
      <div style={{
        background:T.surface, border:`1px solid ${T.border}`,
        padding:"12px 18px", borderRadius:"4px 18px 18px 18px",
        display:"flex", alignItems:"center", gap:6,
      }}>
        <span style={dot(0)}/><span style={dot(.2)}/><span style={dot(.4)}/>
        <span style={{ marginLeft:10, fontSize:13, color:T.red,
                       fontStyle:"italic" }}>{msg}</span>
      </div>
    </div>
  );
}

// ── Markdown + inline [N] citation renderer ────────────────────────────────────
function MDText({ text, sources = [] }) {
  if (!text) return null;

  // Split text into lines, parse each
  const lines = text.split("\n");

  return (
    <div>
      {lines.map((line, li) => {
        if (!line.trim()) return <br key={li} />;

        // Section headers (## or **)
        if (line.startsWith("## ")) {
          return (
            <div key={li} style={{ fontFamily:T.fh, fontWeight:700, fontSize:15,
                                   color:T.text, margin:"16px 0 6px",
                                   borderBottom:`2px solid ${T.red}`,
                                   paddingBottom:4, display:"inline-block" }}>
              {line.slice(3)}
            </div>
          );
        }

        // Bold lines: **text**
        const isFullBold = /^\*\*(.+)\*\*$/.test(line.trim());

        // Tokenise inline: **bold**, `code`, [N] citations
        const tokens = tokenise(line);

        return (
          <p key={li} style={{ margin:"0 0 8px", lineHeight:1.8 }}>
            {tokens.map((tok, ti) => {
              if (tok.type === "bold")
                return <strong key={ti} style={{ color:T.text }}>{tok.text}</strong>;
              if (tok.type === "code")
                return <code key={ti} style={{ background:"#f5f5f5", color:"#d63031",
                  padding:"1px 5px", borderRadius:3,
                  fontFamily:T.ff, fontSize:"0.88em" }}>{tok.text}</code>;
              if (tok.type === "cite") {
                const src = sources.find(s => s.index === tok.n);
                return (
                  <a key={ti} href={src?.url || "#"} target="_blank" rel="noreferrer"
                     className="cite-tag"
                     title={src ? `${src.subreddit} — ${src.title}` : `Source ${tok.n}`}
                     style={{ display:"inline-block", background:T.redDim,
                              color:T.red, padding:"0 5px", borderRadius:4,
                              fontSize:"0.8em", fontWeight:700, margin:"0 2px",
                              textDecoration:"none", transition:"all .15s",
                              verticalAlign:"middle" }}>
                    [{tok.n}]
                  </a>
                );
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
  // Splits a line into: text | bold | code | cite
  const tokens = [];
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d+)\]/g;
  let last = 0, m;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) tokens.push({ type:"text", text: line.slice(last, m.index) });
    if (m[1] !== undefined) tokens.push({ type:"bold", text: m[1] });
    else if (m[2] !== undefined) tokens.push({ type:"code", text: m[2] });
    else if (m[3] !== undefined) tokens.push({ type:"cite", n: parseInt(m[3]) });
    last = m.index + m[0].length;
  }
  if (last < line.length) tokens.push({ type:"text", text: line.slice(last) });
  return tokens;
}

// ── Input Bar ──────────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSend, loading, mode, setMode, textRef, statusMsg }) {
  const onKey = e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  return (
    <div style={{
      position:"sticky", bottom:0, zIndex:40,
      background:"rgba(250,250,250,.97)",
      backdropFilter:"blur(16px)",
      borderTop:`1px solid ${T.border}`,
      padding:"14px 24px 20px",
    }}>
      {/* Mode selector */}
      <div style={{ maxWidth:860, margin:"0 auto 10px",
                    display:"flex", gap:6, alignItems:"center" }}>
        <span style={{ fontSize:10, color:T.muted, letterSpacing:1,
                       textTransform:"uppercase", marginRight:4 }}>mode:</span>
        {[
          { id:"quick", label:"⚡ Quick", hint:"8 posts · ~15s" },
          { id:"deep",  label:"🔬 Deep Research", hint:"30 posts · ~60s" },
        ].map(m => (
          <button key={m.id}
            className={`mode-btn${mode === m.id ? " active" : ""}`}
            onClick={() => setMode(m.id)}
            title={m.hint}
            style={{
              background: mode === m.id ? T.red : T.surface,
              color:      mode === m.id ? "#fff" : T.sub,
              border:     `1px solid ${mode === m.id ? T.red : T.border}`,
              borderRadius:20, padding:"5px 14px",
              fontSize:11, cursor:"pointer",
              transition:"all .18s", fontFamily:T.ff,
            }}>
            {m.label}
          </button>
        ))}
        {loading && statusMsg && (
          <span style={{ marginLeft:"auto", fontSize:11, color:T.red,
                         fontStyle:"italic" }}>{statusMsg}</span>
        )}
      </div>

      {/* Input row */}
      <div style={{ maxWidth:860, margin:"0 auto",
                    display:"flex", gap:10, alignItems:"flex-end" }}>
        <textarea
          ref={textRef}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKey}
          placeholder={mode === "deep"
            ? "Ask a deep question — YAWC will scrape 30 posts…"
            : "Ask anything — YAWC searches Reddit live…"}
          disabled={loading}
          rows={1}
          style={{
            flex:1, background:T.surface,
            border:`1px solid ${T.border}`,
            borderRadius:14, padding:"12px 16px",
            color:T.text, fontFamily:T.ff,
            fontSize:14, lineHeight:1.5,
            resize:"none", outline:"none",
            minHeight:46, maxHeight:140,
            transition:"border-color .2s, box-shadow .2s",
          }}
        />
        <button
          className="send-btn"
          onClick={onSend}
          disabled={loading || !value.trim()}
          style={{
            background: loading || !value.trim() ? "#ddd" : T.red,
            border:"none", borderRadius:12,
            width:46, height:46,
            cursor: loading || !value.trim() ? "not-allowed" : "pointer",
            display:"flex", alignItems:"center", justifyContent:"center",
            flexShrink:0, transition:"all .2s", color:"#fff",
          }}>
          {loading
            ? <div style={{ width:18, height:18, border:"2.5px solid rgba(255,255,255,.4)",
                borderTopColor:"#fff", borderRadius:"50%",
                animation:"spin .65s linear infinite" }} />
            : <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                   stroke="white" strokeWidth="2.2" strokeLinecap="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
          }
        </button>
      </div>
      <div style={{ maxWidth:860, margin:"6px auto 0",
                    fontSize:10, color:T.muted, letterSpacing:.8 }}>
        ↵ Enter to search · Shift+↵ for newline ·
        {mode==="quick" ? " ⚡ Quick: ~8 posts" : " 🔬 Deep: ~30 posts, themes + pros/cons"}
      </div>
    </div>
  );
}
