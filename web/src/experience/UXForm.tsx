import { useState } from "react";
import type { UXRequest } from "../types";

/** The fields and answer buttons of a question from the agent, drawn by the
 * skin inside the question sheet. Answers go back to the reasoning loop that
 * is waiting on this request; skipping and stashing belong to the sheet. */
export default function UXForm({ request, onAnswer }: {
  request: UXRequest;
  onAnswer: (values: Record<string, string>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  // option fields where the user is typing their own answer instead
  const [own, setOwn] = useState<Record<string, boolean>>({});
  const set = (name: string, value: string) => setValues((v) => ({ ...v, [name]: value }));
  const confirms = request.fields.filter((f) => f.kind === "confirm");
  const buttons = request.fields.filter((f) => f.kind === "button");

  return (
    <div className="ux">
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
                <div className="choices">
                  {f.options.map((o) => (
                    <button key={o} className={!own[f.name] && values[f.name] === o ? "on" : ""}
                      onClick={() => { setOwn((x) => ({ ...x, [f.name]: false })); set(f.name, o); }}>{o}</button>
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
          default:
            return null;
        }
      })}
      <div className="actions">
        {confirms.length > 0 ? (
          <>
            <button onClick={() => onAnswer({ ...values, ...Object.fromEntries(confirms.map((c) => [c.name, "no"])) })}>No</button>
            <button className="yes" onClick={() => onAnswer({ ...values, ...Object.fromEntries(confirms.map((c) => [c.name, "yes"])) })}>
              {confirms[0].label || "Yes"}
            </button>
          </>
        ) : buttons.length > 0 ? (
          buttons.map((b) => (
            <button key={b.name} className="yes" onClick={() => onAnswer({ ...values, [b.name]: "pressed" })}>
              {b.label || "OK"}
            </button>
          ))
        ) : (
          <button className="yes" onClick={() => onAnswer(values)}>Send</button>
        )}
      </div>
    </div>
  );
}
