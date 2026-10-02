import { useState } from "react";
import type { UXRequest } from "../types";

/** Generated UI from the agent, drawn by the skin. Answers go back to the
 * reasoning loop that is waiting on this request. */
export default function UXForm({ request, onAnswer }: {
  request: UXRequest;
  onAnswer: (values: Record<string, string>, dismissed?: boolean) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const set = (name: string, value: string) => setValues((v) => ({ ...v, [name]: value }));
  const confirms = request.fields.filter((f) => f.kind === "confirm");
  const buttons = request.fields.filter((f) => f.kind === "button");

  return (
    <div className="ux">
      <div className="kind">{request.purpose === "permission" ? "Needs your OK" : "Quick question"}</div>
      <div className="prompt">{request.prompt}</div>
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
                    <button key={o} className={values[f.name] === o ? "on" : ""} onClick={() => set(f.name, o)}>{o}</button>
                  ))}
                </div>
              </div>
            );
          default:
            return null;
        }
      })}
      <div className="actions">
        <button onClick={() => onAnswer(values, true)}>Not now</button>
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
