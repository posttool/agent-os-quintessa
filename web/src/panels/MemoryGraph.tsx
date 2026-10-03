import { useEffect, useMemo, useRef, useState } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { select } from "d3-selection";
import { drag } from "d3-drag";
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

const radius = (kind: string) => (kind === "topic" ? 8 : kind === "document" ? 7 : 5);
const short = (t: string) => (t.length > 26 ? `${t.slice(0, 25)}…` : t);

/** Facts, topics and documents as a live force-directed graph, after d3's
 * "disjoint force-directed graph" example: forceX/forceY instead of a centering
 * force, so disconnected clusters stay on screen, and nodes can be dragged.
 * Positions are kept between updates so the picture stays stable as memory grows. */
export default function MemoryGraph({ state }: { state: AgentState }) {
  const svgRef = useRef<SVGSVGElement>(null);
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
    return { nodes, links };
  }, [state.memory]);

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl || !nodes.length) return;
    const known = positions.current;
    let fresh = 0;
    for (const n of nodes) {
      const p = known.get(n.id);
      if (p) Object.assign(n, p);
      else fresh++;
    }

    const simulation = forceSimulation(nodes)
      .force("link", forceLink<GNode, GLink>(links).id((d) => d.id).distance(70))
      .force("charge", forceManyBody().strength(-380))
      .force("x", forceX().strength(0.05))
      .force("y", forceY().strength(0.09))
      .force("collide", forceCollide(16))
      // Gentle reheat when only a few nodes are new, so the rest barely move.
      .alpha(known.size && fresh < nodes.length ? Math.min(1, 0.15 + fresh / nodes.length) : 1);

    const svg = select(svgEl);
    svg.selectAll("*").remove();

    const link = svg
      .append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(links)
      .join("line");
    link.append("title").text((d) => label(d.type));

    const node = svg
      .append("g")
      .attr("class", "nodes")
      .selectAll<SVGGElement, GNode>("g")
      .data(nodes)
      .join("g")
      .attr("data-id", (d) => d.id)
      .on("click", (_e, d) => setSelected(d));
    node
      .append("circle")
      .attr("r", (d) => radius(d.kind))
      .attr("fill", (d) => TYPE_COLORS[d.kind] ?? "#888")
      .append("title")
      .text((d) => d.title);
    node
      .append("text")
      .attr("x", (d) => radius(d.kind) + 3)
      .attr("y", 3)
      .text((d) => short(d.title));

    node.call(
      drag<SVGGElement, GNode>()
        .on("start", (event) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          event.subject.fx = event.subject.x;
          event.subject.fy = event.subject.y;
        })
        .on("drag", (event) => {
          event.subject.fx = event.x;
          event.subject.fy = event.y;
        })
        .on("end", (event) => {
          if (!event.active) simulation.alphaTarget(0);
          event.subject.fx = null;
          event.subject.fy = null;
        }),
    );

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as GNode).x!)
        .attr("y1", (d) => (d.source as GNode).y!)
        .attr("x2", (d) => (d.target as GNode).x!)
        .attr("y2", (d) => (d.target as GNode).y!);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
      for (const n of nodes) known.set(n.id, { x: n.x!, y: n.y! });
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, links]);

  useEffect(() => {
    if (!svgRef.current) return;
    select(svgRef.current)
      .selectAll<SVGGElement, GNode>(".nodes g")
      .classed("selected", (d) => d.id === selected?.id);
  }, [selected, nodes]);

  if (!nodes.length) return <div className="empty">Memory is empty. Send the agent something.</div>;
  const kinds = [...new Set(nodes.map((n) => n.kind))];

  return (
    <div>
      <svg ref={svgRef} className="graph" viewBox={`${-W / 2} ${-H / 2} ${W} ${H}`} role="img" aria-label="Memory graph" />
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
