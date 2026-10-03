import { useEffect, useRef, useState } from "react";
import AppIcon from "../components/AppIcon";
import type { Api } from "../api";
import type { AgentState, BriefItem, UXRequest } from "../types";
import { load, save } from "../storage";
import ShadowHost from "./ShadowHost";
import { DEFAULT_SKIN, SKINS } from "./skins";
import UXForm from "./UXForm";
import DocumentView from "./DocumentView";
import CardSheet from "./CardSheet";

type Act = (fn: () => Promise<unknown>) => Promise<void>;
const PAGES = ["Discover", "Home", "Spaces"] as const;

/** The integrated consumer experience: a phone the agent inhabits. It reads
 * only the device state and memory it is handed and talks back through the
 * API, so the skin is replaceable and the agent knows nothing about it. */
export default function Experience({ state, api, act }: { state: AgentState; api: Api; act: Act }) {
  const [skin, setSkin] = useState(() => {
    const saved = load("skin", DEFAULT_SKIN);
    return SKINS[saved] ? saved : DEFAULT_SKIN;
  });
  useEffect(() => save("skin", skin), [skin]);

  return (
    <div style={{ display: "grid", gap: 12, justifyItems: "center" }}>
      <div className="phone-slot">
        <ShadowHost css={SKINS[skin]} theme={document.documentElement.dataset.theme ?? ""}>
          <Phone state={state} api={api} act={act} />
        </ShadowHost>
      </div>
      <label className="small muted row">
        skin
        <select value={skin} onChange={(e) => setSkin(e.target.value)}>
          {Object.keys(SKINS).map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
    </div>
  );
}

function Phone({ state, api, act }: { state: AgentState; api: Api; act: Act }) {
  const [locked, setLocked] = useState(true);
  const [page, setPage] = useState(1);
  const [openDoc, setOpenDoc] = useState<string | null>(null);
  const [sheet, setSheet] = useState<BriefItem | null>(null);
  const pages = useRef<HTMLDivElement>(null);
  const now = useClock();
  const device = state.device;
  const docs = state.memory.documents.filter((d) => d.status !== "archived");
  const topics = new Map(state.memory.topics.map((t) => [t.id, t]));

  // When the agent focuses a document (after a question is answered, or via
  // the device tool), follow it.
  useEffect(() => {
    if (device.focused_document_id) setOpenDoc(device.focused_document_id);
  }, [device.focused_document_id]);

  function go(index: number) {
    setPage(index);
    const el = pages.current;
    if (el) el.scrollTo({ left: index * el.clientWidth, behavior: "smooth" });
  }
  useEffect(() => {
    if (!locked) {
      const el = pages.current;
      if (el) el.scrollLeft = page * el.clientWidth;
    }
  }, [locked]);

  function openDocument(id: string | null, sectionId: string | null = null) {
    if (id) {
      setOpenDoc(id);
      const topicId = state.memory.documents.find((d) => d.id === id)?.topic_id;
      if (topicId && topics.get(topicId)?.new_info) void act(() => api.seen(topicId));
      // A brief item about one section opens the document focused on it.
      if (sectionId) void act(() => api.view(id, [sectionId]));
    }
    setLocked(false);
    setTimeout(() => go(2), 0);
  }

  function answer(r: UXRequest, values: Record<string, string>, dismissed = false) {
    void act(() => api.answer(r.id, values, dismissed));
  }

  // Questions waiting on the user lead the brief, then the agent's own items.
  const needsYou: BriefItem[] = state.pending_ux.map((r) => ({
    id: r.id, text: r.prompt, topic_id: r.topic_id, document_id: r.document_id, section_id: r.section_id, ux_request_id: r.id,
    urgency: "needs-you", detail: "", action: null,
  }));
  // A card past its expires_at is gone even before the server drops it.
  const live = device.brief.filter((b) => !b.expires_at || Date.parse(b.expires_at) > now.getTime());
  const brief = [...needsYou, ...live];

  // An open sheet follows its card: rewritten, it shows the new text; removed,
  // expired or (for a question card) answered, it closes.
  const openCard = !sheet ? null : sheet.ux_request_id
    ? (state.pending_ux.some((r) => r.id === sheet.ux_request_id) ? sheet : null)
    : live.find((b) => b.id === sheet.id) ?? null;
  const sheetGone = sheet !== null && openCard === null;
  useEffect(() => {
    if (sheetGone) setSheet(null);
  }, [sheetGone]);

  function liveDocument(b: BriefItem): string | null {
    // a question belongs to the document it names, not to its topic's
    const id = b.ux_request_id ? b.document_id : b.document_id ?? topics.get(b.topic_id ?? "")?.document_id ?? null;
    return id && docs.some((d) => d.id === id) ? id : null;
  }

  /** Cards with a document open it in Spaces; the rest, and any card with an
   * action to start, open a sheet over the current screen. */
  function tapCard(b: BriefItem) {
    const docId = liveDocument(b);
    if (docId && !b.action) return openDocument(docId, b.section_id);
    if (b.topic_id && topics.get(b.topic_id)?.new_info) void act(() => api.seen(b.topic_id!));
    setSheet(b);
  }

  const sheetQuestions = !openCard ? [] : openCard.ux_request_id
    ? state.pending_ux.filter((r) => r.id === openCard.ux_request_id)
    : state.pending_ux.filter((r) => openCard.topic_id !== null && r.topic_id === openCard.topic_id);
  const sheetDoc = openCard ? liveDocument(openCard) : null;
  const sheetView = openCard && (
    <CardSheet
      item={openCard}
      topic={topics.get(openCard.topic_id ?? "")}
      questions={sheetQuestions}
      onAnswer={(r, values, dismissed) => answer(r, values, dismissed)}
      onAction={() => void act(() => api.briefAct(openCard.id))}
      onAsk={() => { void act(() => api.input(`Tell me more about: ${openCard.text}`)); setSheet(null); }}
      onOpen={sheetDoc ? () => { setSheet(null); openDocument(sheetDoc, openCard.section_id); } : undefined}
      onClose={() => setSheet(null)}
    />
  );

  const briefList = (
    <div className="brief">
      {brief.length === 0 && <div className="brief-empty">Nothing needs you right now.</div>}
      {brief.map((b, i) => (
        <button key={b.ux_request_id ?? b.id ?? i} className={`brief-item ${b.urgency}`} onClick={() => tapCard(b)}>
          <span className="mark" />
          <span className="text">{b.text}</span>
          <span className="cta">›</span>
        </button>
      ))}
    </div>
  );

  const island = (
    <div className={`island ${device.island.active ? "active" : "idle"}`} aria-live="polite">
      {device.island.active && <span className="pulse" />}
      {device.island.active && <span>{device.island.words}</span>}
    </div>
  );

  const clock = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (locked) {
    return (
      <div className="phone">
        {island}
        <div className="lock">
          <div className="clock">{clock.replace(/\s?[AP]M$/i, "")}</div>
          <div className="date">{now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}</div>
          {briefList}
          {device.notifications.length > 0 && (
            <div className="notes">
              {device.notifications.slice(-3).reverse().map((n, i) => <div key={i} className="note">{n}</div>)}
            </div>
          )}
          <button className="unlock" onClick={() => setLocked(false)}>Swipe up to unlock</button>
        </div>
        {sheetView}
      </div>
    );
  }

  const current = docs.find((d) => d.id === openDoc) ?? docs.find((d) => device.space_document_ids.includes(d.id)) ?? docs[0];
  const looseQuestions = state.pending_ux.filter((r) => !r.document_id || !docs.some((d) => d.id === r.document_id));
  const apps = [...state.memory.tools].sort((a, b) => Number(b.kind === "builtin") - Number(a.kind === "builtin"));

  return (
    <div className="phone">
      <div className="statusbar">
        <span>{clock}</span>
        <span onClick={() => setLocked(true)} style={{ cursor: "pointer" }} title="Lock">🔒</span>
      </div>
      {island}
      <div className="pages" ref={pages}
        onScroll={(e) => setPage(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}>
        <section className="page">
          <div className="page-title">Discover</div>
          {device.discovery.length === 0 && (
            <div className="empty">The agent will bring things here that relate to your interests and projects.</div>
          )}
          {device.discovery.map((d, i) => (
            <div key={i} className="discover-card">
              <h4>{d.title}</h4>
              <p>{d.reason}</p>
            </div>
          ))}
        </section>
        <section className="page">
          <div style={{ height: 18 }} />
          {briefList}
          <div className="apps">
            {apps.map((t) => (
              <div key={t.name} className="app" title={t.description}>
                <AppIcon listing={t.listing} name={t.name} glyph={t.name === "web" ? "🌐" : t.name === "device" ? "✦" : undefined} />
                <span>{t.listing?.title ?? t.name.replace(/_/g, " ")}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="page">
          <div className="page-title">Spaces</div>
          {docs.length > 0 && (
            <div className="space-tabs">
              {docs.map((d) => {
                const fresh = d.topic_id && topics.get(d.topic_id)?.new_info;
                const waiting = state.pending_ux.some((r) => r.document_id === d.id);
                return (
                  <button key={d.id} className={current?.id === d.id ? "on" : ""} onClick={() => openDocument(d.id)}>
                    {d.title}
                    {(fresh || waiting) && <span className="new" />}
                  </button>
                );
              })}
            </div>
          )}
          <div style={{ display: "grid", gap: 10 }}>
            {looseQuestions.map((r) => <UXForm key={r.id} request={r} onAnswer={(v, d) => answer(r, v, d)} />)}
            {current ? (
              <DocumentView
                doc={current}
                view={state.views?.[current.id]}
                questions={state.pending_ux.filter((r) => r.document_id === current.id)}
                onAnswer={answer}
                onView={(sectionIds, mode) => void act(() => api.view(current.id, sectionIds, mode))}
              />
            ) : (
              looseQuestions.length === 0 && <div className="empty">Projects you are working on will show up here as the agent learns about them.</div>
            )}
          </div>
        </section>
      </div>
      <div className="dots">
        {PAGES.map((p, i) => (
          <button key={p} className={i === page ? "on" : ""} aria-label={p} title={p} onClick={() => go(i)} />
        ))}
      </div>
      <InputBar onSend={(text, kind) => act(() => api.input(text, kind))} />
      {sheetView}
    </div>
  );
}

function InputBar({ onSend }: { onSend: (text: string, kind: string) => void }) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const Recognition =
    (window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec })
      .SpeechRecognition ??
    (window as unknown as { webkitSpeechRecognition?: new () => SpeechRec }).webkitSpeechRecognition;

  function send(kind = "text", value = text) {
    if (!value.trim()) return;
    onSend(value.trim(), kind);
    setText("");
  }

  function listen() {
    if (!Recognition) return;
    const rec = new Recognition();
    rec.lang = navigator.language;
    rec.onresult = (e) => send("speech", e.results[0][0].transcript);
    rec.onend = () => setListening(false);
    setListening(true);
    rec.start();
  }

  return (
    <div className="inputbar">
      <input placeholder="Ask or tell your agent…" value={text} onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()} />
      {Recognition && (
        <button className={`round ${listening ? "listening" : ""}`} onClick={listen} title="Speak">🎙</button>
      )}
      <button className="round send" onClick={() => send()} title="Send">↑</button>
    </div>
  );
}

interface SpeechRec {
  lang: string;
  onresult: (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void;
  onend: () => void;
  start: () => void;
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000);
    return () => clearInterval(t);
  }, []);
  return now;
}
