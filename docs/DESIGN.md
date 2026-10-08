# WhatToSell Design Doc (v1)

## Positioning

WhatToSell is built for cross-border e-commerce sellers targeting the US market, to help them decide what to sell. A seller enters a product keyword, and the system collects real user discussions and comments from Reddit and TikTok. It organizes them into that category's complaints, what wins buyers over, the questions people ask before buying, and the workarounds they settle for; this is the demand-side validation. The system then takes each "opportunity" inferred from the demand side and checks it against Amazon, TikTok Shop, Temu/AliExpress and 1688, to judge whether the supply side still has room and to estimate sourcing cost and margin. What the seller gets is not a comment summary but a judgment on whether a given product variant is worth launching, together with the evidence behind it.

## Core principle

> **Pipeline-first, agent where uncertainty is high.**
>
> Code controls the process. The LLM controls judgment. The agent controls exploration. Humans handle the exceptions.

The backbone is a deterministic pipeline: what to search, what to collect, what to store and in what order are all fixed in code, so time and cost per search are predictable and every report has the same structure. Models are brought in at four levels of increasing freedom, and each piece of work is assigned to the lowest level that can do it well:

| Level | Who decides | Used for | Examples in v1 |
|---|---|---|---|
| 0 Deterministic | Code | Fetching, storing, deduplicating, scoring | Collection adapters, cleaning rules, heat score |
| 1 LLM | One bounded model call with a fixed output schema | Classification, naming, summarizing, extraction | Keyword discovery, cluster naming, coverage check, opportunity generation |
| 2 Agent | A model loop that chooses its own next step, within a budget | Open-ended investigation where the path can't be specified in advance | Supply-side verification: "prove whether supply for this opportunity actually exists" |
| 3 Human | The operator | High-value or low-confidence exceptions | Reviewing verdicts flagged low-confidence |

What separates this product from one person running an ad-hoc agent session is that the agent sits inside a structured product. The agent may explore freely, but its output never goes straight to the UI. It must be turned into structured evidence that conforms to a fixed schema, and the final report is assembled from that evidence. When a new task turns out to need open-ended exploration, it plugs into the same agent execution layer; the architecture doesn't change.

## Confirmed decisions

| Area | Decision |
|---|---|
| Target users | Cross-border e-commerce sellers (TikTok Shop / Amazon) making product-selection decisions |
| Market | United States |
| Channels | v1 covers Reddit and TikTok only; Instagram moves to v2, with its adapter interface reserved now |
| Report granularity | A keyword-level cross-channel aggregate report first, plus drill-down into any single post or video for its own comment analysis |
| Scope | v1 includes both the demand side and the supply side |
| Supply-side sources | Amazon, TikTok Shop, Temu/AliExpress, 1688 sourcing prices |
| Search depth | User-selectable tiers; deeper tiers cost more credits, which can later double as pricing tiers |
| Monetization | v1 has account login and usage credits, with no payments yet |
| LLM | Fixed LLM tasks go through a provider-agnostic layer, switchable between Claude, DeepSeek and other models. The agent layer starts on a single provider and sits behind its own runtime interface |

## Architecture

```
User input
   ↓
Job + credit charge
   ↓
① Discovery            L1  expand the keyword; find relevant subreddits and hashtags
   ↓
② Collection           L0  per-channel adapters
   ↓
③ Cleaning / dedup     L0 (+ L1 relevance filter)
   ↓
④ Clustering + classification   L0 clustering, L1 naming and four-category assignment
   ↓
④b Coverage check      L1  "what did we miss?" (one bounded rework round)
   ↓
⑤ Opportunity generation         L1
   ↓
┌────────────────────────────────────────┐
│ ⑥ Agent verification layer        L2   │
│    search → inspect → compare          │
│       ↑                  ↓             │
│       └────── retry ─────┘             │
│    budget: steps / runtime / cost /    │
│            searches / pages            │
└───────────────────┬────────────────────┘
                    ↓
          Structured evidence (fixed schema)
                    ↓
⑦ Verdict + confidence  L1 verdict; confidence computed from evidence
                    ↓
Final report (fixed JSON schema) → UI
                    ↓
Low confidence → flagged in report + operator review queue   L3
```

Infrastructure: a Next.js frontend (three-pane workbench) talks to a FastAPI backend over REST, with SSE for progress. A search takes 3–10 minutes, so it runs as a background job (arq + Redis). Data and the raw-data cache live in Postgres.

Both the collection layer and the supply side are split into swappable adapters, one per platform. Each adapter is responsible only for converting its platform's data into the shared data structures. This keeps data sources replaceable: when a source becomes unreliable or a better one is available, only its adapter changes, and the analysis code above it is untouched.

## Demand-side analysis

**Discovery.** Before collecting, one LLM call expands the seller's keyword into closely related search terms (for example, "camping chair" also covers "beach chair" and "folding chair") and identifies the subreddits and hashtags where the product is discussed. This decides where collection looks, so it is done once and reused by every channel.

**Cleaning and clustering.** Collected comments are cleaned first, removing emoji-only comments, comments that only tag friends, obvious bot accounts, and anything unrelated to the keyword. The cleaned comments are grouped by topic clustering. The LLM then names each cluster and assigns it to one of four fixed categories: what people complain about, what wins them over, what they ask, and what workarounds they settle for.

Each category carries three things: a comment count, a like-weighted heat score, and a few verbatim user quotes as evidence. Every report must also state where its sample came from and how it is biased, for example "these are the platform's top-ranked comments, not a random sample". Sellers will spend real money on inventory based on this report, so every conclusion must trace back to the original comments.

Clustering before handing off to the LLM, rather than feeding all eight thousand comments to the LLM directly, comes down to two things: it cuts cost by about an order of magnitude, and it produces far more consistent categories across runs on the same input.

**Coverage check.** A first-pass classification can quietly miss things, and a missed pain point is exactly the kind of error a seller can't see. After the first pass, the system therefore asks "what did we miss?" rather than just "is anything unassigned?":

```
Initial classification
   ↓
Collect unassigned comments + low-confidence assignments
   ↓
LLM review: is there an important pattern here?
   ├── No  → ignore; record the residual size in the sampling note
   └── Yes → create a candidate cluster → re-classify affected comments once
   ↓
Final demand report
```

The rework runs at most once per report, so cost stays bounded. The report records how many comments the check examined and whether it added a cluster, so coverage is auditable.

**Opportunities.** The LLM reads the finished report and proposes 3–8 opportunities, each phrased as a concrete product-variant hypothesis (for example, "a beach chair rated for 150 kg+ that folds into a shoulder-carry") and linked to the clusters that support it.

## Supply-side verification

### What gets verified

Verification is the most expensive step, so only the top-ranked opportunities are verified, by tier: the top 2 on Light, top 3 on Standard, and top 5 on Deep. The rest are shown as "not verified" and can be verified later on request.

### The verification agent

Verifying an opportunity is an open-ended investigation: if the first search finds nothing, try other wording; when a competitor turns up, open it and read its negative reviews; when the evidence is thin, keep looking. This is the one place in v1 where a Level 2 agent is used. Its task is: **prove whether supply for this opportunity actually exists, and how good it is.**

The agent has a fixed toolset: web search, page fetch, the Amazon data adapter, and a tool to record each piece of evidence as it finds it. It decides for itself which tools to use and in what order, for example:

```
web search → search results → competitor sites → Amazon / TikTok Shop / Temu
   → reviews → evidence insufficient → change keywords → search again → …
```

1688 sourcing prices come from the same loop, but in v1 they are only an estimated range flagged "needs manual review".

### Structured evidence

The agent's free-form reasoning is never shown to users directly. It must finish by submitting evidence in this fixed shape, which is validated before anything downstream uses it:

```json
{
  "opportunity_id": "…",
  "existing_solutions": [
    {
      "name": "…",
      "platform": "amazon | tiktok_shop | temu | aliexpress | 1688 | web",
      "url": "…",
      "price": 29.99,
      "evidence": "verbatim review or listing detail",
      "source": "api | agent_search",
      "strength": "weak | medium | strong"
    }
  ],
  "market_gap": "…",
  "sourcing_price_range": { "low": 4.5, "high": 7.0, "currency": "USD", "needs_manual_review": true }
}
```

A Level 1 call then reads this evidence and returns one of three verdicts, citing specific competitors and verbatim reviews:

- **Nobody does it**: the opportunity holds, but first work out why nobody is doing it.
- **Done poorly**: the best case; competitors' negative reviews become your spec for the improved version.
- **Done well**: drop it; don't fight an entrenched competitor.

### Confidence is computed, not self-reported

A model's own "0.82" isn't calibrated, and sellers would read it as a precise probability. Confidence is computed from the evidence instead and shown as three levels:

| Level | Rule |
|---|---|
| High | At least 3 independent solutions across at least 2 platforms, at least one from an API source, and the evidence points consistently at the verdict |
| Medium | Neither high nor low |
| Low | Fewer than 2 solutions found, all evidence from agent web search, or the agent hit its budget before finishing |

### Human review (Level 3)

Human review never blocks a report. Low-confidence verdicts are shown with an "evidence is thin — verify before acting" label, and are also placed in an operator review queue. The operator can confirm, correct or retract a verdict after the fact, and corrections become evaluation data for improving the agent.

## Agent execution layer

The agent is not a feature of one phase; it is a controlled execution layer that any pipeline step can call. Every call goes through one interface:

```
run(task, tools, budget, output_schema) -> AgentResult
```

The runtime behind this interface starts on a single LLM provider, chosen for speed of development, and can be swapped for another without changing callers.

**Budget.** Every agent job runs under hard limits, enforced by the runtime rather than requested of the model:

| Limit | Default per verification job |
|---|---|
| max_steps | 20 |
| max_runtime | 5 min |
| max_llm_cost | $0.20 |
| max_searches | 10 |
| max_pages | 20 |

There is also a supply-side budget per search, so a Deep search verifying five opportunities can't exceed its tier's cost ceiling. When any limit is hit, the agent is asked to submit the evidence it has so far, and the result is marked as budget-terminated, which forces low confidence.

**Step log.** Every step is recorded: step number, tool, input, output (truncated), tokens, cost and duration. This makes each verdict auditable, and it makes cost measurable — for example, "one opportunity verification averages $0.08, P95 $0.17" — which is what credit pricing is based on.

## Depth tiers and credits

| Tier | Per channel | Opportunities verified | Expected time | Credits |
|---|---|---|---|---|
| Light | 10 posts × 100 comments | Top 2 | 2–4 min | 1 |
| Standard | 20 posts × 200 comments | Top 3 | 4–10 min | 3 |
| Deep | 50 posts × 500 comments | Top 5 | 10–20 min | 8 |

A repeat search for the same keyword within 24 hours reuses the raw data already collected and only re-runs the analysis, at a discounted credit cost.

## Core data model

- `users`: user accounts and remaining credits.
- `searches`: a single search, with its keyword, tier, status and the LLMs used.
- `posts`: posts and videos found by searches, with channel, external ID, title, view and like counts, and link.
- `comments`: comments, with parent post, text, like count, publish time and whether each is a reply.
- `demand_reports`: demand-side reports. Each search has one aggregate report, and each post can also have its own per-post report. Records coverage-check results.
- `insight_clusters`: one cluster within a report, recording which of the four categories it belongs to, its title, count, heat score, representative quotes, and whether it was added by the coverage check.
- `opportunities`: opportunities derived from the demand side, with rank and verification status (not verified, verified, budget-terminated).
- `agent_runs`: one agent job — task type, budget, status, totals for steps, tokens, cost and duration.
- `agent_steps`: one step of an agent run — tool, input, output, tokens, cost, duration.
- `supply_checks`: the structured evidence for one opportunity on one platform, with competitors, prices, negative reviews and source type.
- `verdicts`: the final verdict, reasoning, computed confidence and review status for each opportunity.

## Phases

1. **Skeleton**: monorepo and Docker Compose (Postgres + Redis), the FastAPI skeleton, adapter interfaces and shared data structures, and the LLM layer.
2. **Collection**: Reddit and TikTok adapters, plus async jobs and progress streaming.
3. **Demand side and agent layer**: discovery, clustering, the four-category breakdown, coverage check, opportunity generation, aggregate and per-post reports, and the agent execution layer (runtime interface, budgets, step log).
4. **Frontend**: the three-pane workbench, search history and report pages.
5. **Supply side**: the verification agent, the Amazon adapter, structured evidence, verdicts and computed confidence.
6. **Accounts, credits and launch readiness**: sign-up and login, credit charging, depth tiers, operator review queue, deployment.
7. **v2**: Instagram, proper 1688 integration, Stripe payments, follow-up questions on a finished report.

Each phase's deliverables, acceptance criteria and open decisions are in [ROADMAP.md](ROADMAP.md).

## Key risks

The first is data access: platform policies change, so every data source must stay replaceable behind its adapter. The second is stability: TikTok's anti-bot measures keep evolving, so adapters need retries, proxies and graceful degradation, and each channel's health must be visible. The third is per-search cost: agent verification is the most variable cost in the system, which is why it runs under hard budgets, only the top opportunities are verified, and every step's cost is logged so credit pricing can be set from measured data rather than estimates.
