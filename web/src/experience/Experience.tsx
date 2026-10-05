import { useEffect, useRef, useState } from "react";
import AppIcon from "../components/AppIcon";
import type { Api } from "../api";
import type { AgentState, Card, Question } from "../types";
import { load, save } from "../storage";
import ShadowHost from "./ShadowHost";
import { DEFAULT_SKIN, SKINS } from "./skins";
import DocumentView from "./DocumentView";
import CardSheet from "./CardSheet";
import QuestionDeck, { QuestionStack, SheetPeek, WaitingRow, deckOrder, questionGroups } from "./QuestionDeck";

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
  const [sheet, setSheet] = useState<Card | null>(null);
  // the question sheet: the waiting questions, or the stash, tapped one
  // first; opened from one topic's brief item, only that topic's questions
  const [deck, setDeck] = useState<{ stash: boolean; first: string | null; group?: string | null } | null>(null);
  const pages = useRef<HTMLDivElement>(null);
  const now = useClock();
  const device = state.device;
  const docs = state.memory.documents.filter((d) => d.status !== "archived");
  const topics = new Map(state.memory.topics.map((t) => [t.id, t]));

  // When the agent focuses a document (after a question is answered, or via
  // the device tool), Spaces shows it next time the user comes to it; it
  // never swaps the document out from under someone reading Spaces.
  useEffect(() => {
    if (device.focused_document_id && (locked || page !== 2)) setOpenDoc(device.focused_document_id);
  }, [device.focused_document_id, locked, page]);

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

  // Every question the agent asks is answered in the question sheet. Waiting
  // ones stack at the top of the brief; stashed ones wait in a pile after it.
  const stashedIds = new Set((device.stashed ?? []).map((q) => q.question_id));
  const waiting = state.questions.filter((r) => !stashedIds.has(r.id));
  const stashed = state.questions.filter((r) => stashedIds.has(r.id));
  const groups = questionGroups(waiting, topics, docs);

  function openQuestion(r: Question | null, stash = stashedIds.has(r?.id ?? "")) {
    setSheet(null);
    setDeck({ stash, first: r?.id ?? null });
  }

  // A card past its expires_at is gone even before the server drops it.
  const live = device.brief.filter((b) => !b.expires_at || Date.parse(b.expires_at) > now.getTime());

  // An open sheet follows its card: rewritten, it shows the new text; removed
  // or expired, it closes.
  const openCard = !sheet ? null : live.find((b) => b.id === sheet.id) ?? null;
  const sheetGone = sheet !== null && openCard === null;
  useEffect(() => {
    if (sheetGone) setSheet(null);
  }, [sheetGone]);

  function liveDocument(b: Card): string | null {
    const id = b.document_id ?? topics.get(b.topic_id ?? "")?.document_id ?? null;
    return id && docs.some((d) => d.id === id) ? id : null;
  }

  /** Cards with a document open it in Spaces; the rest, and any card with an
   * action to start, open a sheet over the current screen. */
  function tapCard(b: Card) {
    const docId = liveDocument(b);
    void act(() => api.cardOpen(b.id));
    if (docId && !b.action) return openDocument(docId, b.section_id);
    if (b.topic_id && topics.get(b.topic_id)?.new_info) void act(() => api.seen(b.topic_id!));
    setSheet(b);
  }

  const sheetQuestions = !openCard ? [] : state.questions.filter((r) => openCard.topic_id !== null && r.topic_id === openCard.topic_id);
  const sheetDoc = openCard ? liveDocument(openCard) : null;
  const sheetView = openCard && (
    <CardSheet
      card={openCard}
      topic={topics.get(openCard.topic_id ?? "")}
      questions={sheetQuestions}
      onQuestion={(r) => openQuestion(r)}
      onAction={() => void act(() => api.cardAct(openCard.id))}
      onAsk={() => { void act(() => api.input(`Tell me more about: ${openCard.text}`)); setSheet(null); }}
      onOpen={sheetDoc ? () => { setSheet(null); openDocument(sheetDoc, openCard.section_id); } : undefined}
      onSnooze={() => { void act(() => api.cardSnooze(openCard.id)); setSheet(null); }}
      onDismiss={() => { void act(() => api.cardDismiss(openCard.id)); setSheet(null); }}
      onClose={() => setSheet(null)}
    />
  );

  const pool = !deck ? [] : deck.stash ? stashed : deck.group ? groups.find((g) => g.key === deck.group)?.questions ?? [] : waiting;
  const deckQuestions = !deck ? [] : deckOrder(pool, deck.first);
  const deckView = deck && deckQuestions.length > 0 && (
    <QuestionDeck
      key={deck.stash ? "stash" : deck.group ?? "waiting"}
      questions={deckQuestions}
      stash={deck.stash}
      topics={topics}
      docs={docs}
      onAnswer={(r, values, selections) => void act(() => api.answer(r.id, values, false, selections))}
      onSkip={(r) => void act(() => api.answer(r.id, {}, true))}
      onStash={(rs) => rs.forEach((r) => void act(() => api.stash(r.id)))}
      onUnstash={(r) => void act(() => api.unstash(r.id))}
      onOpen={(docId, sectionId) => { setDeck(null); openDocument(docId, sectionId); }}
      onClose={() => setDeck(null)}
    />
  );

  // The agent never opens a sheet by itself. While questions wait, the
  // question sheet peeks in from the bottom edge; the user pulls it up.
  const peekView = !deck && !sheet && waiting.length > 0 && (
    <SheetPeek questions={waiting} onOpen={() => openQuestion(waiting[0], false)} />
  );

  const briefList = (
    <div className="brief">
      {waiting.length === 0 && live.length === 0 && <div className="brief-empty">Nothing needs you right now.</div>}
      {groups.map((g) => (
        <QuestionStack key={g.key} group={g}
          onOpen={() => { setSheet(null); setDeck({ stash: false, first: g.questions[0].id, group: g.key }); }} />
      ))}
      {live.map((b) => (
        <button key={b.id} className={`brief-item ${b.urgency}`} onClick={() => tapCard(b)}>
          <span className="mark" />
          <span className="text">{b.text}</span>
          <span className="cta">›</span>
        </button>
      ))}
      {stashed.length > 0 && (
        <button className="stash-chip" onClick={() => openQuestion(stashed[0], true)}>
          {stashed.length} stashed {stashed.length === 1 ? "question" : "questions"}
        </button>
      )}
    </div>
  );

  // While the agent waits on the user, the island opens the oldest question.
  const island = (
    <div className={`island ${device.island.active ? "active" : "idle"} ${waiting.length ? "tappable" : ""}`} aria-live="polite"
      onClick={waiting.length ? () => openQuestion(waiting[0], false) : undefined}
      role={waiting.length ? "button" : undefined}>
      {device.island.active && <span className="pulse" />}
      {device.island.active && <span>{device.island.words}</span>}
    </div>
  );

  const clock = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (locked) {
    return (
      <div className={`phone ${peekView ? "peeking" : ""}`}>
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
        {peekView}
        {sheetView}
        {deckView}
      </div>
    );
  }

  const current = docs.find((d) => d.id === openDoc) ?? docs.find((d) => device.space_document_ids.includes(d.id)) ?? docs[0];
  const looseQuestions = state.questions.filter((r) => !r.document_id || !docs.some((d) => d.id === r.document_id));
  const apps = [...state.memory.tools].sort((a, b) => Number(b.kind === "builtin") - Number(a.kind === "builtin"));

  return (
    <div className={`phone ${peekView ? "peeking" : ""}`}>
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
                const waiting = state.questions.some((r) => r.document_id === d.id);
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
            {looseQuestions.map((r) => <WaitingRow key={r.id} request={r} stashed={stashedIds.has(r.id)} onOpen={() => openQuestion(r)} />)}
            {current ? (
              <DocumentView
                doc={current}
                view={state.views?.[current.id]}
                questions={state.questions.filter((r) => r.document_id === current.id)}
                stashedIds={stashedIds}
                onQuestion={(r) => openQuestion(r)}
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
      {peekView}
      {sheetView}
      {deckView}
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
