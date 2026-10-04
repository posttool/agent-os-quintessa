import { useEffect, useState } from "react";
import type { Doc, DocumentSection, DocView, UXRequest, ViewMode } from "../types";
import { WaitingRow } from "./QuestionDeck";

/** A document in Spaces. Only the sections that matter now are expanded;
 * the rest fold into an outline the user can open one tap at a time, or all
 * at once. A question tied to a section shows under it as a row that opens it
 * in the question sheet. */
export default function DocumentView({ doc, view, questions, stashedIds, onQuestion, onView }: {
  doc: Doc;
  view: DocView | undefined;
  questions: UXRequest[];
  stashedIds: Set<string>;
  onQuestion: (r: UXRequest) => void;
  onView: (sectionIds: string[] | null, mode?: ViewMode) => void;
}) {
  const serverOpen = view?.section_ids ?? doc.sections.map((s) => s.id);
  const serverMode = view?.mode ?? "focused";
  // Taps apply at once; the server's answer (via the state stream) replaces them.
  const [open, setOpen] = useState<string[]>(serverOpen);
  const [mode, setMode] = useState<ViewMode>(serverMode);
  const [more, setMore] = useState(false);
  const [allDates, setAllDates] = useState(false);
  useEffect(() => {
    setOpen(serverOpen);
    setMode(serverMode);
  }, [doc.id, serverOpen.join(","), serverMode]);
  useEffect(() => {
    setMore(false);
    setAllDates(false);
  }, [doc.id]);

  const full = mode === "full";
  const changed = new Set(view?.changed_section_ids ?? []);
  const sectionIds = new Set(doc.sections.map((s) => s.id));
  const isOpen = (s: DocumentSection) => full || open.includes(s.id);
  const loose = questions.filter((q) => !q.section_id || !sectionIds.has(q.section_id));
  const dates = full || allDates ? doc.key_dates : doc.key_dates.slice(0, 1);
  const extras = doc.observations.length + doc.links.length;

  function toggle(id: string) {
    const next = open.includes(id) ? open.filter((x) => x !== id) : [...open, id];
    setOpen(next);
    onView(next, "focused");
  }
  function showFull() {
    setMode("full");
    onView(open, "full");
  }
  function backToFocus() {
    setMode("focused");
    onView(null);
  }

  return (
    <div className="doc">
      <div>
        <h2>{doc.title}</h2>
        <span className="chip">{doc.status}</span>
      </div>
      {full && doc.description && <p className="desc">{doc.description}</p>}
      {doc.progress_overview && <p className="desc">{doc.progress_overview}</p>}
      {!full && view?.reason && <p className="why">{view.reason}</p>}
      {loose.map((q) => <WaitingRow key={q.id} request={q} stashed={stashedIds.has(q.id)} onOpen={() => onQuestion(q)} />)}
      {dates.length > 0 && (
        <div className="block">
          <div className="label">{dates.length < doc.key_dates.length ? "Next date" : "Key dates"}</div>
          {dates.map((k, i) => (
            <div key={i} style={{ fontSize: 13, marginTop: 4 }}>
              <span className={`chip ${k.tentative ? "tentative" : ""}`}>{k.tentative ? "penciled in" : "set"}</span> {k.when} · {k.label}
            </div>
          ))}
          {dates.length < doc.key_dates.length && (
            <button className="link-button" onClick={() => setAllDates(true)}>All dates ({doc.key_dates.length})</button>
          )}
        </div>
      )}
      {doc.sections.map((s) => {
        const asks = questions.filter((q) => q.section_id === s.id);
        return (
          <div key={s.id}>
            {isOpen(s) ? (
              <SectionBlock section={s} focused={!full || open.includes(s.id)} fresh={changed.has(s.id)}
                onFold={full ? undefined : () => toggle(s.id)} />
            ) : (
              <button className="outline-row" onClick={() => toggle(s.id)} aria-expanded={false}>
                {changed.has(s.id) && <span className="new" />}
                <span className="title">{s.title}</span>
                {s.status && <span className="chip">{s.status}</span>}
                <span className="cta">›</span>
              </button>
            )}
            {asks.map((q) => (
              <div key={q.id} style={{ marginTop: 8 }}>
                <WaitingRow request={q} stashed={stashedIds.has(q.id)} onOpen={() => onQuestion(q)} />
              </div>
            ))}
          </div>
        );
      })}
      {extras > 0 && (full || more) && (
        <>
          {doc.observations.length > 0 && (
            <div className="block">
              <div className="label">Relevant observations</div>
              <ul>{doc.observations.map((o, i) => <li key={i}>{o}</li>)}</ul>
            </div>
          )}
          {doc.links.length > 0 && (
            <div className="block links">
              <div className="label">Links</div>
              {doc.links.map((l) => <a key={l} href={l} target="_blank" rel="noreferrer">{l}</a>)}
            </div>
          )}
        </>
      )}
      <div className="doc-actions">
        {!full && extras > 0 && !more && <button className="link-button" onClick={() => setMore(true)}>More</button>}
        {full
          ? <button className="link-button" onClick={backToFocus}>Back to focus</button>
          : doc.sections.length > 0 && <button className="link-button" onClick={showFull}>Show full document</button>}
      </div>
    </div>
  );
}

function SectionBlock({ section: s, focused, fresh, onFold }: {
  section: DocumentSection; focused: boolean; fresh: boolean; onFold?: () => void;
}) {
  return (
    <div className={`block ${focused ? "focus" : ""}`}>
      <h4 onClick={onFold} style={onFold ? { cursor: "pointer" } : undefined} title={onFold ? "Fold" : undefined}>
        <span>{fresh && <span className="new" />}{s.title}</span>
        {s.status && <small>{s.status}</small>}
      </h4>
      {s.overview && <p>{s.overview}</p>}
      {s.details && <p>{s.details}</p>}
      {s.actions_taken.length > 0 && (
        <>
          <div className="label">Done</div>
          <ul>{s.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </>
      )}
      {s.suggested_actions.length > 0 && (
        <>
          <div className="label">Next</div>
          <ul>{s.suggested_actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </>
      )}
    </div>
  );
}
