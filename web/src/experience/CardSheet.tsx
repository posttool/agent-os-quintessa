import { useState } from "react";
import type { BriefItem, Salience, Topic, UXRequest } from "../types";
import UXForm from "./UXForm";
import { ago } from "../format";

/** A brief card that has no document to open: what it is about, its open
 * questions and the one thing it proposes, over whatever screen is showing. */
export default function CardSheet({ item, topic, questions, onAnswer, onAction, onAsk, onOpen, onSnooze, onDismiss, onClose }: {
  item: BriefItem;
  topic: Topic | undefined;
  questions: UXRequest[];
  onAnswer: (r: UXRequest, values: Record<string, string>, dismissed?: boolean) => void;
  onAction: () => void;
  onAsk: () => void;
  onOpen?: () => void;
  onSnooze?: () => void;
  onDismiss?: () => void;
  onClose: () => void;
}) {
  const [started, setStarted] = useState(false);
  const action = item.action;
  const args = Object.entries(action?.arguments ?? {});
  // A question card is its question; its prompt already says what the card says.
  const asksOnly = item.ux_request_id !== null;

  return (
    <div className="sheet-scrim" onClick={onClose}>
      <div className="sheet" role="dialog" aria-label={item.text} onClick={(e) => e.stopPropagation()}>
        <div className="grip" />
        {!asksOnly && (
          <>
            <div className="sheet-title">{item.text}</div>
            {item.updated_at && <div className="sheet-age">Updated {ago(item.updated_at)}</div>}
            {item.salience && <div className="sheet-age" title={`scored by ${item.salience.scored_by}`}>{whyRanked(item.salience)}</div>}
            {item.detail && <p className="sheet-detail">{item.detail}</p>}
            {topic && (
              <div className="sheet-topic">
                {topic.title !== item.text && <div className="sheet-topic-title">{topic.title}</div>}
                {topic.summary && <p>{topic.summary}</p>}
                {topic.new_info && <p className="new-info">{topic.new_info}</p>}
                <div>
                  {topic.due && <span className="chip">Due {topic.due}</span>}
                  {topic.progress > 0 && <span className="chip">{Math.round(topic.progress * 100)}% done</span>}
                </div>
              </div>
            )}
          </>
        )}
        {questions.map((r) => <UXForm key={r.id} request={r} onAnswer={(v, d) => onAnswer(r, v, d)} />)}
        {action && (
          <div className="sheet-action">
            <button className="primary" disabled={started} onClick={() => { setStarted(true); onAction(); }}>
              {started ? "On it" : action.label}
            </button>
            <div className="sheet-args">
              {action.tool}.{action.function}
              {args.map(([k, v]) => <div key={k}>{k}: {v}</div>)}
            </div>
          </div>
        )}
        <div className="sheet-buttons">
          {onOpen && <button onClick={onOpen}>Open document</button>}
          {!asksOnly && <button onClick={onAsk}>Ask about this</button>}
          {onSnooze && <button onClick={onSnooze} title="Hide for an hour">Not now</button>}
          {onDismiss && <button onClick={onDismiss}>Dismiss</button>}
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

/** "Rank 0.71: urgency 0.8 · soon 0.9 · fits now 0.6 · person 0.7" */
function whyRanked(s: Salience): string {
  const parts: [string, number | null][] = [
    ["urgency", s.urgency], ["soon", s.proximity], ["fits now", s.relevance], ["person", s.affinity],
    ["pushed away", s.suppression || null],
  ];
  const shown = parts.filter(([, v]) => v !== null).map(([k, v]) => `${k} ${(v as number).toFixed(1)}`);
  return `Rank ${s.score.toFixed(2)}: ${shown.join(" · ")}`;
}
