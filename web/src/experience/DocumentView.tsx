import type { Doc, UXRequest } from "../types";
import UXForm from "./UXForm";

/** A document in Spaces. Questions tied to one of its sections render in
 * place, so answering returns the user to the context that asked. */
export default function DocumentView({ doc, focusedSection, questions, onAnswer }: {
  doc: Doc;
  focusedSection: string | null;
  questions: UXRequest[];
  onAnswer: (r: UXRequest, values: Record<string, string>, dismissed?: boolean) => void;
}) {
  const sectionIds = new Set(doc.sections.map((s) => s.id));
  const loose = questions.filter((q) => !q.section_id || !sectionIds.has(q.section_id));
  return (
    <div className="doc">
      <div>
        <h2>{doc.title}</h2>
        <span className="chip">{doc.status}</span>
      </div>
      {doc.description && <p className="desc">{doc.description}</p>}
      {doc.progress_overview && <p className="desc">{doc.progress_overview}</p>}
      {loose.map((q) => <UXForm key={q.id} request={q} onAnswer={(v, d) => onAnswer(q, v, d)} />)}
      {doc.key_dates.length > 0 && (
        <div className="block">
          <div className="label">Key dates</div>
          {doc.key_dates.map((k, i) => (
            <div key={i} style={{ fontSize: 13, marginTop: 4 }}>
              <span className={`chip ${k.tentative ? "tentative" : ""}`}>{k.tentative ? "penciled in" : "set"}</span> {k.when} · {k.label}
            </div>
          ))}
        </div>
      )}
      {doc.sections.map((s) => (
        <div key={s.id}>
          <div className={`block ${s.id === focusedSection ? "focus" : ""}`}>
            <h4>{s.title}{s.status && <small>{s.status}</small>}</h4>
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
          {questions.filter((q) => q.section_id === s.id).map((q) => (
            <div key={q.id} style={{ marginTop: 8 }}>
              <UXForm request={q} onAnswer={(v, d) => onAnswer(q, v, d)} />
            </div>
          ))}
        </div>
      ))}
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
    </div>
  );
}
