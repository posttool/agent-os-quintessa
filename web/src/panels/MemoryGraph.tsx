import { useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationNodeDatum } from "d3-force";
import type { AgentState } from "../types";
import { label } from "../format";

export const TYPE_COLORS: Record<string, string> = {
  topic: "#5b4ce0",
  document: "#d9488f",
  personal_preference: "#1d8a5a",
  project_context: "#2f7fd8",
  ambient_state: "#8a8a80",
  tool_knowledge: "#b7791f",
  active_process: "#e0612f",
  person: "#0f9fae",
  routine: "#7a5bb5",
};

interface GNode extends SimulationNodeDatum {
  id: string;
  title: string;
  kind: string;
  detail: string;
}
interface GLink {
  source: string | GNode;
  target: string | GNode;
  type: string;
}

const W = 760;
const H = 420;

/** Facts, topics and documents as one force-directed graph. Positions are
 * kept between updates so the picture stays stable as memory grows. */
export default function MemoryGraph({ state }: { state: AgentState }) {
  const positions = useRef(new Map<string, { x: number; y: number }>());
  const [selected, setSelected] = useState<GNode | null>(null);

  const { nodes, links } = useMemo(() => {
    const m = state.memory;
    const nodes: GNode[] = [
      ...m.topics.filter((t) => !t.archived).map((t) => ({ id: t.id, title: t.title, kind: "topic", detail: t.summary })),
      ...m.documents
        .filter((d) => d.status !== "archived")
        .map((d) => ({ id: d.id, title: d.title, kind: "document", detail: d.description })),
      ...m.nodes.map((n) => ({ id: n.id, title: n.title, kind: n.type as string, detail: n.body })),
    ];
    const ids = new Set(nodes.map((n) => n.id));
    const links: GLink[] = [
      ...m.edges.map((e) => ({ source: e.source_id, target: e.target_id, type: e.type })),
      ...m.nodes.filter((n) => n.topic_id).map((n) => ({ source: n.id, target: n.topic_id!, type: "in topic" })),
      ...m.topics.filter((t) => t.parent_id).map((t) => ({ source: t.id, target: t.parent_id!, type: "subtopic of" })),
      ...m.documents.filter((d) => d.topic_id).map((d) => ({ source: d.id, target: d.topic_id!, type: "documents" })),
    ].filter((l) => ids.has(l.source as string) && ids.has(l.target as string));

    for (const n of nodes) {
      const p = positions.current.get(n.id);
      if (p) Object.assign(n, p);
    }
    const sim = forceSimulation(nodes)
      .force("link", forceLink<GNode, GLink>(links).id((d) => d.id).distance(90))
      .force("charge", forceManyBody().strength(-320))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide(18))
      .stop();
    sim.tick(positions.current.size ? 80 : 300);
    for (const n of nodes) {
      n.x = Math.max(20, Math.min(W - 20, n.x ?? 0));
      n.y = Math.max(20, Math.min(H - 20, n.y ?? 0));
      positions.current.set(n.id, { x: n.x, y: n.y });
    }
    return { nodes, links };
  }, [state.memory]);

  if (!nodes.length) return <div className="empty">Memory is empty. Send the agent something.</div>;
  const kinds = [...new Set(nodes.map((n) => n.kind))];

  return (
    <div>
      <svg className="graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Memory graph">
        {links.map((l, i) => {
          const s = l.source as GNode;
          const t = l.target as GNode;
          return <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y}><title>{label(l.type)}</title></line>;
        })}
        {nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`} onClick={() => setSelected(n)}>
            <circle r={n.kind === "topic" ? 9 : n.kind === "document" ? 8 : 6} fill={TYPE_COLORS[n.kind] ?? "#888"}>
              <title>{n.title}</title>
            </circle>
            <text x={11} y={4}>{n.title.length > 26 ? `${n.title.slice(0, 25)}…` : n.title}</text>
          </g>
        ))}
      </svg>
      <div className="legend">
        {kinds.map((k) => (
          <span key={k}>
            <i style={{ background: TYPE_COLORS[k] ?? "#888" }} />
            {label(k)}
          </span>
        ))}
      </div>
      {selected && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="row">
            <strong className="grow">{selected.title}</strong>
            <span className="badge">{label(selected.kind)}</span>
            <code className="faint">{selected.id}</code>
            <button className="ghost" onClick={() => setSelected(null)}>✕</button>
          </div>
          {selected.detail && <p style={{ margin: "6px 0 0" }}>{selected.detail}</p>}
        </div>
      )}
    </div>
  );
}
