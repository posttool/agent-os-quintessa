# Plan: Jev in Quintessa's reasoning loop

> **Date:** 2026-10-02  
> **Status:** Partly built. Shadow mode and the Jev ambient filter shipped in [PR #7](https://github.com/posttool/agent-os-quintessa/pull/7); Jev scores in Traces in [#8](https://github.com/posttool/agent-os-quintessa/pull/8); an opt-in "let Jev choose the next step" setting in [#9](https://github.com/posttool/agent-os-quintessa/pull/9); Jev given the LLM's full decide context in [#10](https://github.com/posttool/agent-os-quintessa/pull/10). The hybrid decider and focus-free executors were not built.  
> **Source:** [plan doc](https://claude.ai/code/artifact/8c53ccb6-5e1e-4f8d-8ddc-ff7f6f9eb1df), copied as written.


## Results so far (Oct 2)

The setup: Claude Opus drove 8 triggers (Jane's dinner, booking it, Mom's flight, a newsletter, "show me the dinner plan", moving dinner to 8, arriving at work, "what do I need to do before Mom gets here?"). I recorded all 68 decision states and replayed them through `jev-1.13.0`. Agreement means Jev picked the same next step as Claude.

| Version | Agreement | Notes |
| --- | --- | --- |
| Trimmed state (PR #7 as is) | 34% | Picks memory for only 6 of the 25 decisions where Claude did |
| Trimmed + memory nodes, document sections, what this trigger already saved | 41% |  |
| Same, with rewritten memory and tool\_use criteria | 46% |  |
| Claude's full prompt state (\~35k chars) | 53% | Best single-Choice result |
| Yes/no facts, with code choosing the step (jev2ui's approach) | 50% | Memory recall rises to 17/25, but "needs the user" fires too often |
| Facts, thresholds tuned on half the data, tested on the other half | 62% | Tuned on 34 decisions, so treat it as optimistic |

Latency stayed around 550–650 ms per decision across every version. Confidence did not reliably mark the safe cases: in the second run, decisions at 0.9 or higher agreed with Claude only 4 out of 7 times.

**Reading.** Choosing the next step depends on reading the whole chain: what's already saved, what's been asked, what's been done. Jev doesn't do that well enough to take over the loop. Claude isn't a clean label either: it repeats memory steps, and it hit the 12-step limit once. So part of the gap may be noise in the labels, not Jev.

**Recommendation.** Keep shadow mode for data collection, but don't route any loop decision through Jev yet. The most promising narrow use is still the ambient pre-filter ("does this event matter at all?"). That needs its own test on a larger ambient stream, with labels checked by a person rather than taken from Claude.

### Ambient pre-filter test (Oct 2)

I wrote 60 ambient events across messages, the door camera, location and notifications, and labeled them by hand: 23 that matter and 37 that are noise. The labels are in `/mnt/project-files/jev-eval/ambient_events.csv`. Jev answered one yes/no question per event ("does this matter?"), either with the event alone or with the event plus an outline of memory (the topics, documents and people already being tracked). The comparison is Claude's first controller decision: anything other than "done" counts as "matters".

| Filter | Accuracy | Signal missed (of 23) | Noise let through (of 37) | Sessions skipped (of 60) |
| --- | --- | --- | --- | --- |
| Jev, event only, p ≥ 0.5 | 58% | 1 | 24 | 14 |
| **Jev + memory, p ≥ 0.3** | 87% | **0** | 8 | **29** |
| Jev + memory, p ≥ 0.5 | 93% | 3 | 1 | 39 |
| Jev + memory, p ≥ 0.7 | 83% | 10 | 0 | 47 |
| Claude (first step not "done") | 83% | 0 | 10 | 27 |

The median decision took 617 ms for Jev and 6.0 s for Claude. At p ≥ 0.3, Jev missed nothing that mattered and skipped about half of all sessions. That's slightly better than Claude, at a tenth of the time. At 0.5, it missed a flight check-in, a bill due date and a coffee invitation.

Caveats: there are only 60 events, and I wrote both the labels and the question, so Duke should check the labels. Memory context makes a large difference: without it, Jev can't tell "Mom's flight delayed" apart from a bank statement.

## What "Jev" is

I took "jev" to mean **Jev from TypeSafe AI**, a "System One" decision model. It doesn't generate text. You send it a `state` (text or JSON) plus named typed questions, and it returns a calibrated answer for each one:

- **Choice**: pick one label from a set. Returns `choice`, `probabilities` per label, and `confidence`.
- **Score**: place the state on an ordered rubric. Returns an expected `score`, per-level `probabilities`, and `confidence`.
- **Noul**: yes/no. Returns `noul`, the probability of yes.

This matches your example ("choosing the next step"), and it's what every search result for "jev agent loop" points to. TypeSafe claims up to 200x faster and 400x cheaper than an LLM on classification tasks. That's their number, not one I've measured. Nothing in your GitHub repos is called jev. The only other close name I found is *jive* (merijjeyn/jive), a wiki essay on the same System One idea, not a runnable model.

The API, checked against the `typesafe-sdk` 0.7.2 source on PyPI:

```python
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

async with AsyncTypeSafeClient() as client:          # TYPESAFE_API_KEY, model "jev-latest", 10s timeout
    r = await client.system_one(
        state={...},                                    # text, JSON object or array
        questions={"next": Choice(instructions="...", criteria={"memory": "...", "done": "..."})},
    )
    r.choices["next"].choice, r.choices["next"].probabilities, r.choices["next"].confidence
```

Several questions can be asked about the same state in one call. That matters below.

## Open-source option: gev

Jev itself is a hosted, closed model. Its weights aren't published. The open alternative is **[gev](https://github.com/dglazkov/gev)** (Apache-2.0), which [jev2ui](https://github.com/dglazkov/jev2ui) uses as a drop-in second endpoint. A setting in jev2ui picks jev or gev per request, both through the same `@typesafe-ai/sdk` client (`src/server/models.ts`).

- **It's a reimplementation of the API, not of the model.** gev serves the same `POST /v1/systemone` request and response format, so a TypeSafe client pointed at a gev base URL works unchanged. In our Python SDK that's `base_url=` or `TYPESAFE_BASE_URL`.
- **How it works:** each question becomes one prompt to an open LLM (Gemma 4 26B-A4B, FP8, served by vLLM). Each answer option gets a one-token label, the model generates exactly one token, and gev turns the top-20 logprobs into a probability per option. `confidence` is 1 minus normalized entropy.
- **Where it runs:** a Cloud Run GPU (RTX PRO 6000) with deploy scripts in the repo. Any vLLM or SGLang server works, including a smaller `gemma-4-E4B-it`.
- **Speed:** the README reports parity with jev, about 130 ms for 18 questions.
- **Caveat from its own README:** these are raw token probabilities, not calibrated outcomes, and letter labels carry position bias (`GEV_ROTATIONS` averages over rotated orders). That makes the calibration step in Phase 2 more important, not less.

**What this changes in the plan.** `JevDecider` becomes a System One client with a configurable base URL, so jev, a hosted gev, or our own gev are a config switch: `QUINTESSA_SYSTEM_ONE_URL`, defaulting to TypeSafe's. Phase 2 can then compare jev and gev on the same recorded states. Ways to get a gev endpoint, from least to most work:

1. Use the gev that dglazkov runs (jev2ui's default `GEV_BASE_URL`). This needs a key from them.
2. Deploy gev in your own GCP project. This needs GPU quota in the region, and the README says the model server takes about ten minutes to cold-start, so it keeps one instance warm.
3. Build the same logprob trick into Quintessa against Gemini on Vertex, which already exists as an adapter. *Inferred, not checked:* Vertex Gemini exposes top-k logprobs. Claude's API doesn't, so this route would be Gemini only.

## How the loop decides today

Everything below goes through `ResilientLLM.generate_json`. A session that takes N steps makes about **2N+1 LLM calls**: one `decide` per step, one capability call per step, and a final `decide` that returns `done`.

| # | Decision | Where | What the LLM returns | Can Jev do it? |
| --- | --- | --- | --- | --- |
| 1 | **Next capability or done** | `loop/reasoning_loop.py` `decide()` | `capability` (an enum of 4 + `done`), `focus` (free text), `rationale`, `status_words` | **Yes, for the choice.** `focus` is free text, so it has to come from somewhere else (see below) |
| 2 | Which tool to call | `executors/tool_use_executor.py` (`tool` enum) | tool, function, arguments, document/section ids, progress stages, permission prompt | **Tool and function, yes.** Arguments and prompt, no |
| 3 | What kind of question to ask | `executors/generative_ui_executor.py` (`purpose` enum) | purpose, prompt, form fields | Purpose only. That saves little, because the fields still need the LLM |
| 4 | Whether a new tool is needed | `executors/tool_discovery_executor.py` | a tool definition | Partly: a yes/no "does an existing tool already cover this?" before discovery runs |
| 5 | Memory operations | `executors/memory_executor.py` | nodes, edges, topics, documents | No, this is generation |
| 6 | Simulated tool results and ambient data | `tools/runner.py`, `ambient/generator.py` | invented content | No |
| 7 | Permission gate | `needs_permission()` | n/a, already plain code | No change needed |

Two more places aren't LLM calls today, but they're natural fits for Jev:

- **Ambient pre-filter.** Every ambient event and progress report calls `runtime.submit()` and starts a full session. The controller prompt itself says many of these "need only a memory step, or nothing at all." A Noul ("does this event change anything the agent tracks?") could skip the whole session for noise.
- **Topic triggers.** `memory/apply.py` stores each topic's `triggers` (type, condition), but no code ever checks them. The LLM only reads them as part of memory. A Noul per trigger against each incoming event would turn them into real rules.

## The main design problem: `focus`

`decide()` does two jobs at once. It picks the capability, and it writes `focus`, the instruction the capability's own LLM call follows. Jev can do the first job but not the second. Three ways to handle it:

1. **Executors write their own focus (my default).** Each capability call already gets the trigger, steps so far, memory and on-screen state (`executors/common.py` `call_capability`). Drop `focus` from the decision and add one line to the capability prompts: "you were chosen as the next step; work out the most useful thing to do." Jev's top probabilities go in as the rationale. This removes the `decide` LLM call completely.
2. Jev picks, and a small fast LLM writes focus. This keeps the current executor contract but saves only latency, not a call.
3. Use Jev only to decide **done vs. continue**, a Noul, and keep the LLM for everything else. This is the safest option, and it still saves the final `decide` call in every session.

`status_words` becomes a fixed label per capability ("Saving", "Asking", "Finding tools", "Working"), with no model involved.

## Architecture

A new `quintessa/decide/` package with one small interface, so the loop doesn't know which backend answered:

```python
class Decider(Protocol):
    async def choose(self, name: str, state: dict, options: dict[str, str], instructions: str) -> Decision: ...

@dataclass
class Decision:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    source: str        # "jev:jev-latest" or "claude:claude-opus-5-5"
    latency_ms: float
```

- `LLMDecider` wraps today's `generate_json` call, so current behavior stays byte-for-byte the same.
- `JevDecider` wraps `AsyncTypeSafeClient.system_one`, with options built from each capability's `description` (front matter in `capabilities/*.md`).
- `ShadowDecider(primary, shadow)` acts on the primary's answer and records the shadow's answer next to it.
- `HybridDecider(jev, llm, threshold)` uses Jev when `confidence >= threshold` and otherwise falls back to the LLM.
- A fake `ScriptedDecider` for the tests, like the existing `Script` in `tests/conftest.py`.

`TraceStep` gains a `decision` field (source, probabilities, confidence, latency, and the shadow's answer if there is one), so the Traces panel can show where the two backends disagree. Configuration follows the existing env style: `QUINTESSA_DECIDER=llm|shadow|hybrid` (default `llm`), `QUINTESSA_JEV_THRESHOLD=0.8`, and `QUINTESSA_TYPESAFE_API_KEY`, read first and passed as `api_key=`, the same pattern as the Anthropic key.

**State sent to Jev.** Today `decide` sends the full memory snapshot. For Jev I'd start with a trimmed state: the trigger, steps so far (capability, summary, error), topic titles and progress, and what's on screen. The eval compares trimmed against full, because a smaller state is cheaper and may be clearer.

## Evaluation plan

**Phase 0: Access (needs you).** The cloud sandbox's egress proxy blocks `api.typesafe.ai` (I got a 403). PyPI works, so the SDK installs. We need a TypeSafe API key and `api.typesafe.ai` added to the environment's network allowlist. Until then, everything below runs against the fake decider.

**Phase 1: Shadow mode.** Add the Decider interface and `ShadowDecider(llm, jev)`. The LLM still drives every session, and Jev's answer is recorded on each step. Run the existing persona simulation and ambient templates (`persona/simulation.py`, `samples/ambient_templates.json`) to collect a few hundred real decision states with both answers.

**Phase 2: Offline eval.** `python -m quintessa eval-decider` replays recorded states and reports:

- agreement with the LLM's choice, overall and per capability (a confusion matrix)
- agreement with a small hand-labeled gold set (about 50 states I label from the traces and you spot-check), because the LLM isn't always right either
- calibration: accuracy per confidence bucket, which tells us where to set the threshold
- coverage at each threshold: the share of decisions Jev handles while staying at 95% or better agreement
- latency p50/p95, and tokens per decision, for both backends
- the same metrics for trimmed vs. full state

The report gets published as an artifact.

**Phase 3: Hybrid on the next-step choice.** Turn on `HybridDecider` at the chosen threshold, with option 1 for focus. Compare end to end against the LLM-only loop on the same scripted scenarios: steps per session, how often it asks the user, failed or repeated steps, and wall-clock time. Ship only if session quality holds.

**Phase 4: Extend if Phase 3 holds,** in order of expected payoff:

1. Ambient pre-filter, which skips whole sessions
2. Done vs. continue as its own Noul (if Phase 3 used the combined choice)
3. Tool choice and function choice in `tool_use`
4. Topic trigger checks
5. "Does an existing tool cover this?" before `tool_discovery`

## Defaults I picked

- Jev means TypeSafe's model. Alternatives: *jive*, a concept wiki, not a model.
- Option 1 for `focus`: executors write their own, so the `decide` LLM call goes away.
- Start with the next-step choice only, and keep the LLM as the fallback below the threshold.
- Starting threshold 0.8, to be replaced by whatever the calibration data says.
- Default `QUINTESSA_DECIDER=llm`, so nothing changes until we turn it on.

## Work, as PRs

1. **Decider interface + shadow mode.** Covers `decide/`, the `TraceStep.decision` field, `JevDecider` (using `typesafe-sdk`), and tests with the fake decider. No behavior change.
2. **Eval command + recorded dataset + report.**
3. **Hybrid next-step choice + focus-free executors,** behind the flag.
4. **Ambient pre-filter and the other Phase 4 items,** one at a time.

## Unknowns

- TypeSafe's pricing, rate limits, and limits on option count and state size. Their docs site is blocked from the sandbox, so I couldn't read them. Four or five options for the next step is a small Choice, so it shouldn't hit a limit.
- Whether Jev handles the order-dependent part of the loop well ("don't repeat a step that already succeeded with the same focus"). Phase 2's confusion matrix will show this.

## Sources

- [Jev on OpenRouter docs](https://openrouter.ai/docs/guides/community/jev)
- [TypeSafe quick start](https://docs.typesafe.ai/introduction/quickstart)
- [Building a harness with Jev (LangChain)](https://www.langchain.com/blog/building-a-harness-with-jev)
- [jive wiki: Rethinking the agentic loop with System One models](https://github.com/merijjeyn/jive/wiki)
- `typesafe-sdk` 0.7.2 on PyPI, read directly
