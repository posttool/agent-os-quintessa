from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from statistics import median

from quintessa.models import ReasoningSession, ShadowDecision

BUCKETS = [(0.9, 1.01), (0.8, 0.9), (0.6, 0.8), (0.0, 0.6)]


def agreement_report(sessions: Iterable[ReasoningSession]) -> str:
    """How often the System One model picked the step the LLM picked:
    overall, per LLM choice, by the model's confidence, and how fast."""
    decisions = [d for s in sessions for d in s.shadow_decisions if not d.drove]
    answered = [d for d in decisions if not d.error]
    if not decisions:
        return "No shadow decisions recorded yet. Set QUINTESSA_JEV_API_KEY and run some sessions."
    lines = [
        f"{len(decisions)} decisions in shadow, {len(answered)} answered, {len(decisions) - len(answered)} failed",
    ]
    if answered:
        lines.append(f"agreement with the LLM: {_rate(answered)}")
        lines.append("")
        lines.append("by LLM choice (what the System One model picked instead):")
        by_llm: dict[str, list[ShadowDecision]] = defaultdict(list)
        for d in answered:
            by_llm[d.llm_choice].append(d)
        for llm_choice, group in sorted(by_llm.items()):
            picked = Counter(d.choice for d in group if not d.agrees)
            others = ", ".join(f"{c} x{n}" for c, n in picked.most_common())
            lines.append(f"  {llm_choice:<15} {_rate(group):<16} {others}")
        lines.append("")
        lines.append("by confidence (agreement, share of decisions):")
        for low, high in BUCKETS:
            group = [d for d in answered if low <= d.confidence < high]
            if group:
                lines.append(
                    f"  {low:.1f}-{min(high, 1.0):.1f}  {_rate(group):<16} "
                    f"{len(group) / len(answered):.0%} of decisions"
                )
        latencies = sorted(d.latency_ms for d in answered)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        lines.append("")
        lines.append(f"latency: median {median(latencies):.0f} ms, p95 {p95:.0f} ms")
    errors = Counter(d.error for d in decisions if d.error)
    if errors:
        lines.append("")
        lines.append("failures:")
        lines.extend(f"  x{n} {error[:120]}" for error, n in errors.most_common(5))
    return "\n".join(lines)


def _rate(group: list[ShadowDecision]) -> str:
    agreed = sum(d.agrees for d in group)
    return f"{agreed}/{len(group)} ({agreed / len(group):.0%})"
