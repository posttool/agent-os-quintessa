import { useEffect, useRef, useState } from "react";
import type { Doc, Topic, Question, Selection } from "../types";
import QuestionForm from "./QuestionForm";

/** The one place the agent's questions are answered: a sheet holding a deck
 * of them. The top question is full size with the next two peeking out
 * behind it; answering, skipping or stashing it brings up the next, and a
 * sideways swipe moves through the deck without answering. `stash` decks
 * hold the questions the user put aside. */
export default function QuestionDeck({ questions, stash, topics, docs, onAnswer, onSkip, onStash, onUnstash, onOpen, onClose }: {
  questions: Question[];
  stash: boolean;
  topics: Map<string, Topic>;
  docs: Doc[];
  onAnswer: (r: Question, values: Record<string, string>, selections: Record<string, Selection[]>) => void;
  onSkip: (r: Question) => void;
  onStash: (rs: Question[]) => void;
  onUnstash: (r: Question) => void;
  onOpen: (documentId: string, sectionId: string | null) => void;
  onClose: () => void;
}) {
  // Questions just handled leave at once; the state stream confirms it.
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [pos, setPos] = useState(0);
  const deck = questions.filter((q) => !gone.has(q.id));
  const at = Math.min(pos, Math.max(deck.length - 1, 0));
  const top = deck[at];
  const empty = deck.length === 0;
  useEffect(() => {
    if (empty) onClose();
  }, [empty]);
  const touch = useRef<number | null>(null);
  if (!top) return null;

  function done(rs: Question[]) {
    setGone((g) => new Set([...g, ...rs.map((r) => r.id)]));
  }
  const step = (by: number) => setPos(Math.min(Math.max(at + by, 0), deck.length - 1));
  const topic = top.topic_id ? topics.get(top.topic_id) : undefined;
  const doc = top.document_id ? docs.find((d) => d.id === top.document_id) : undefined;
  const section = doc && top.section_id ? doc.sections.find((s) => s.id === top.section_id) : undefined;
  const args = Object.entries(top.arguments ?? {});
  const behind = Math.min(deck.length - 1 - at, 2);

  return (
    <div className="sheet-scrim" onClick={onClose}>
      <div className="sheet deck" role="dialog" aria-label={top.prompt} onClick={(e) => e.stopPropagation()}>
        <div className="grip" />
        <div className="deck-head">
          <span className="kind">{stash ? "Stashed" : KIND[top.purpose] ?? "Quick question"}</span>
          {deck.length > 1 && (
            <span className="deck-count">
              <button aria-label="Previous question" disabled={at === 0} onClick={() => step(-1)}>‹</button>
              {at + 1} of {deck.length}
              <button aria-label="Next question" disabled={at === deck.length - 1} onClick={() => step(1)}>›</button>
            </span>
          )}
        </div>
        <div className={`deck-stack behind-${behind}`}>
          {Array.from({ length: behind }, (_, i) => <div key={i} className={`deck-peek peek-${i + 1}`} />)}
          <div key={top.id} className="deck-card"
            onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
            onTouchEnd={(e) => {
              const dx = e.changedTouches[0].clientX - (touch.current ?? e.changedTouches[0].clientX);
              if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1);
              touch.current = null;
            }}>
            <div className="sheet-title">{top.prompt}</div>
            {top.context && <p className="deck-why">{top.context}</p>}
            {(topic || section) && (
              <div className="sheet-topic">
                {topic && <div className="sheet-topic-title">{topic.title}</div>}
                {section ? (
                  <p><strong>{section.title}</strong>{section.overview && `: ${section.overview}`}</p>
                ) : (
                  topic?.summary && <p>{topic.summary}</p>
                )}
              </div>
            )}
            {top.purpose === "permission" && top.tool && (
              <div className="sheet-args">
                {top.tool}.{top.function}
                {args.map(([k, v]) => <div key={k}>{k}: {v}</div>)}
              </div>
            )}
            <QuestionForm key={top.id} request={top} onAnswer={(values, selections) => { done([top]); onAnswer(top, values, selections); }} />
          </div>
        </div>
        <div className="sheet-buttons">
          {doc && <button onClick={() => onOpen(doc.id, top.section_id)}>Open document</button>}
          <button onClick={() => { done([top]); onSkip(top); }} title="Go on without an answer">Skip</button>
          {stash ? (
            <button onClick={() => { done([top]); onUnstash(top); }}>Back to stack</button>
          ) : (
            <>
              <button onClick={() => { done([top]); onStash([top]); }} title="Answer later">Stash</button>
              {deck.length > 1 && <button onClick={() => { done(deck); onStash(deck); }}>Stash all</button>}
            </>
          )}
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

const KIND: Partial<Record<Question["purpose"], string>> = { permission: "Needs your OK", next_step: "Next step" };

/** The agent waits on the user: a stack of the questions waiting, with the
 * oldest on top, that opens the deck. */
export function QuestionStack({ questions, onOpen }: { questions: Question[]; onOpen: () => void }) {
  if (questions.length === 0) return null;
  const many = questions.length > 1;
  return (
    <button className={`brief-item needs-you ${many ? "stack" : ""}`} onClick={onOpen}>
      <span className="mark" />
      <span className="text">
        {questions[0].prompt}
        {many && <span className="more">{questions.length - 1} more {questions.length === 2 ? "question" : "questions"}</span>}
      </span>
      {many && <span className="count">{questions.length}</span>}
      <span className="cta">›</span>
    </button>
  );
}

/** Where a question used to be drawn inline: one row that opens it. */
export function WaitingRow({ request, stashed = false, onOpen }: { request: Question; stashed?: boolean; onOpen: () => void }) {
  return (
    <button className={`waiting-row ${stashed ? "stashed" : ""}`} onClick={onOpen}>
      <span className="kind">{stashed ? "Stashed" : "Waiting on you"}</span>
      <span className="text">{request.prompt}</span>
      <span className="cta">›</span>
    </button>
  );
}

/** The deck's order: the question tapped first, then the rest of its topic,
 * then the others oldest first. */
export function deckOrder(questions: Question[], firstId: string | null): Question[] {
  const first = questions.find((q) => q.id === firstId);
  if (!first) return questions;
  const same = questions.filter((q) => q !== first && first.topic_id !== null && q.topic_id === first.topic_id);
  return [first, ...same, ...questions.filter((q) => q !== first && !same.includes(q))];
}
