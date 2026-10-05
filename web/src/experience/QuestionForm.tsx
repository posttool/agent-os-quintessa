import { useState } from "react";
import type { Question, QuestionField, Selection } from "../types";
import PictureView from "./PictureView";

const MAX_QUANTITY = 99;

/** The fields and answer buttons of a question from the agent, drawn by the
 * skin inside the question sheet. Answers go back to the reasoning loop that
 * is waiting on this request; skipping and stashing belong to the sheet. */
export default function QuestionForm({ request, onAnswer }: {
  request: Question;
  onAnswer: (values: Record<string, string>, selections: Record<string, Selection[]>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  // multi_option fields: what is picked, with how many, in tap order
  const [picked, setPicked] = useState<Record<string, Selection[]>>({});
  // option fields where the user is typing their own answer instead
  const [own, setOwn] = useState<Record<string, boolean>>({});
  const set = (name: string, value: string) => setValues((v) => ({ ...v, [name]: value }));
  const multi = request.fields.filter((f) => f.kind === "multi_option");
  function answer(extra: Record<string, string> = {}) {
    const selections = Object.fromEntries(multi.map((f) => {
      const typed = own[f.name] && values[f.name]?.trim() ? [{ option: values[f.name].trim(), quantity: 1 }] : [];
      return [f.name, [...(picked[f.name] ?? []), ...typed]];
    }));
    const text = Object.fromEntries(multi.map((f) => [f.name, describe(selections[f.name])]));
    onAnswer({ ...values, ...text, ...extra }, selections);
  }
  const confirms = request.fields.filter((f) => f.kind === "confirm");
  const buttons = request.fields.filter((f) => f.kind === "button");

  return (
    <div className="question">
      {request.fields.map((f) => {
        switch (f.kind) {
          case "display_text":
            return <div key={f.name} className="fieldlabel">{f.label || f.options.join(" ")}</div>;
          case "free_text":
          case "number":
          case "location":
            return (
              <label key={f.name}>
                {f.label && <div className="fieldlabel">{f.kind === "location" ? "📍 " : ""}{f.label}</div>}
                <input type={f.kind === "number" ? "number" : "text"} value={values[f.name] ?? ""}
                  onChange={(e) => set(f.name, e.target.value)} />
              </label>
            );
          case "option":
          case "suggestion":
            return (
              <div key={f.name}>
                {f.label && <div className="fieldlabel">{f.label}</div>}
                <div className={`choices ${pictured(f) ? "pictured" : ""}`}>
                  {f.options.map((o) => (
                    <button key={o} className={!own[f.name] && values[f.name] === o ? "on" : ""}
                      onClick={() => { setOwn((x) => ({ ...x, [f.name]: false })); set(f.name, o); }}>
                      <ChoiceLabel field={f} option={o} />
                    </button>
                  ))}
                  <button className={`other ${own[f.name] ? "on" : ""}`}
                    onClick={() => { setOwn((x) => ({ ...x, [f.name]: true })); set(f.name, ""); }}>Something else…</button>
                </div>
                {own[f.name] && (
                  <input autoFocus placeholder="Say what you'd like" value={values[f.name] ?? ""}
                    onChange={(e) => set(f.name, e.target.value)} />
                )}
              </div>
            );
          case "multi_option": {
            const chosen = picked[f.name] ?? [];
            const count = (o: string) => chosen.find((c) => c.option === o)?.quantity ?? 0;
            const setCount = (o: string, n: number) => setPicked((p) => {
              const was = p[f.name] ?? [];
              const next = was.some((c) => c.option === o)
                ? was.map((c) => (c.option === o ? { option: o, quantity: n } : c))
                : [...was, { option: o, quantity: n }];
              return { ...p, [f.name]: next.filter((c) => c.quantity > 0) };
            });
            return (
              <div key={f.name}>
                <div className="fieldlabel">{f.label ? `${f.label} · ` : ""}pick any</div>
                <div className={`choices multi ${pictured(f) ? "pictured" : ""}`}>
                  {f.options.map((o) => {
                    const n = count(o);
                    const quantity = f.option_details?.find((d) => d.option === o)?.takes_quantity ?? false;
                    return (
                      <div key={o} className={`choice-row ${n > 0 ? "on" : ""}`}>
                        <button className="pick" aria-pressed={n > 0} onClick={() => setCount(o, n > 0 ? 0 : 1)}>
                          <span className="check" aria-hidden>{n > 0 ? "✓" : ""}</span>
                          <ChoiceLabel field={f} option={o} />
                        </button>
                        {quantity && n > 0 && (
                          <span className="stepper" aria-label={`How many ${o}`}>
                            <button aria-label="One fewer" onClick={() => setCount(o, n - 1)}>−</button>
                            <span className="qty">{n}</span>
                            <button aria-label="One more" disabled={n >= MAX_QUANTITY} onClick={() => setCount(o, n + 1)}>+</button>
                          </span>
                        )}
                      </div>
                    );
                  })}
                  <button className={`other ${own[f.name] ? "on" : ""}`}
                    onClick={() => setOwn((x) => ({ ...x, [f.name]: !x[f.name] }))}>Something else…</button>
                </div>
                {own[f.name] && (
                  <input autoFocus placeholder="Add something else" value={values[f.name] ?? ""}
                    onChange={(e) => set(f.name, e.target.value)} />
                )}
              </div>
            );
          }
          default:
            return null;
        }
      })}
      <div className="actions">
        {confirms.length > 0 ? (
          <>
            <button onClick={() => answer(Object.fromEntries(confirms.map((c) => [c.name, "no"])))}>No</button>
            <button className="yes" onClick={() => answer(Object.fromEntries(confirms.map((c) => [c.name, "yes"])))}>
              {confirms[0].label || "Yes"}
            </button>
          </>
        ) : buttons.length > 0 ? (
          buttons.map((b) => (
            <button key={b.name} className="yes" onClick={() => answer({ [b.name]: "pressed" })}>
              {b.label || "OK"}
            </button>
          ))
        ) : (
          <button className="yes" onClick={() => answer()}>Send</button>
        )}
      </div>
    </div>
  );
}

const pictured = (f: QuestionField) => (f.option_details ?? []).some((d) => d.picture);

/** An option's label, with the picture a tool returned for it beside it. */
function ChoiceLabel({ field, option }: { field: QuestionField; option: string }) {
  const picture = field.option_details?.find((d) => d.option === option)?.picture;
  return (
    <>
      {picture && <PictureView picture={picture} size="thumb" />}
      <span className="choice-label">{option}</span>
    </>
  );
}

/** A multi-select answer as the agent reads it: "2 × Margherita, Coke". */
function describe(selections: Selection[]): string {
  return selections.map((s) => (s.quantity > 1 ? `${s.quantity} × ${s.option}` : s.option)).join(", ") || "none";
}
