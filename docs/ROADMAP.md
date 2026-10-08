# WhatToSell Roadmap

This document expands the seven phases in the [design doc](DESIGN.md) into an executable plan. For each phase it states what gets delivered, the key technical approach, what "done" means (acceptance criteria), and what needs to be supplied or decided before work starts.

The architecture follows one principle from the design doc: **pipeline-first, agent where uncertainty is high**. Code controls the process, the LLM controls judgment, the agent controls exploration, and humans handle the exceptions.

The phases depend on each other as follows. Collection in phase 2 is the foundation for everything after it. Phase 3 builds both the demand-side analysis and the agent execution layer; the opportunities it produces are the input to supply-side verification in phase 5, and the verification agent in phase 5 runs on the layer built in phase 3. The frontend in phase 4 can be built in parallel once the report structure from phase 3 is settled. Accounts and credits in phase 6 do not depend on the analysis pipeline and can be slotted in at any point, but must be finished before the product is opened to outside users.

| Phase | Scope | Status | Estimate |
|---|---|---|---|
| 1 | Skeleton | ✅ Done (2026-10-07) | — |
| 2 | Collection: Reddit + TikTok | Next | 3–5 days |
| 3 | Demand side + agent execution layer | Not started | 7–9 days |
| 4 | Frontend workbench | Not started | 5–7 days |
| 5 | Supply-side verification agent + verdicts | Not started | 6–9 days |
| 6 | Accounts, credits, launch readiness | Not started | 4–6 days |
| 7 | v2: Instagram, 1688, payments, paid data sources | Not started | TBD |

Estimates assume one full-time developer working with AI assistance and are mainly for sequencing. Concrete dates are in the schedule below.

## Schedule: launch before December 20

"Launch" here means phase 6 is complete: invited outside users can sign up, receive credits, run searches and read reports, with no payments yet. Phase 7 is outside this deadline.

December 20 falls on a Sunday, so the launch date is set to **Friday, December 18**, leaving the weekend as a final buffer. There are 52 working days from October 8 to December 18, while phases 2–6 need 36 working days at their upper estimates. Every phase is therefore scheduled at or above its upper estimate, with a dedicated beta-testing window at the end. Adding the agent execution layer cost two days, taken from the beta window.

| Phase | Dates | Working days | Milestone |
|---|---|---|---|
| 2 Collection | Oct 8 – Oct 16 | 7 | Oct 16: all three test keywords collect reliably |
| 3 Demand side + agent layer | Oct 19 – Nov 3 | 12 | Nov 3: a complete demand report (with coverage check) from the command line; agent runtime passes its budget tests |
| 4 Frontend | Nov 4 – Nov 17 | 10 | Nov 17: the full flow, from search to per-post drill-down, works in the browser |
| 5 Supply side | Nov 18 – Dec 1 | 10 | Dec 1: reports show all three verdict types with structured evidence and computed confidence |
| 6 Accounts & launch readiness | Dec 2 – Dec 11 | 8 | Dec 11: deployed to production, beta accounts working |
| Beta & fixes | Dec 14 – Dec 17 | 4 | 3–5 real sellers try it; fix what they find |
| **Launch** | **Fri, Dec 18** | — | Invite-only sign-up opens |

Progress is checked at the end of each phase. If a phase overruns, the beta window is compressed first, and scope is cut only after that. The first cut is TikTok Shop and Temu from the verification agent's reach (verdicts then rely on Amazon plus the 1688 estimate); the second is per-post reports. Agent budgets, structured evidence and the step log are never cut: without them, cost can't be controlled. The keyword-level aggregate report and the Amazon-based verdict are the core of the product and will not be cut.

**Items to start early.** These depend on outside approvals or need the owner to act personally. Each must be done before the phase that needs it starts, or development will stall:

| Due | Item | Why |
|---|---|---|
| Oct 8 | Provide Reddit and TikTok access credentials (in `.env`) | Needed on day one of phase 2 |
| Oct 16 | Submit the application for commercial use of Reddit's Data API | Approval time is unknown and may take weeks; it must be in hand before launch |
| Oct 23 | Hand-label about 300 comments for each of the three test keywords | This gold set is the acceptance test for phase 3 |
| Oct 30 | Decide whether to review a frontend mockup first | Determines how phase 4 starts |
| Nov 13 | Choose the Amazon data provider and open an account; provide default freight and fee assumptions | Needed on day one of phase 5 |
| Nov 20 | Settle on the auth approach, hosting platform, free credit grant and tier pricing; register a domain | Needed for phase 6; the domain and email sending must be configured in advance |
| Dec 4 | Line up 3–5 sellers willing to beta test | The beta window starts Dec 14 |
| Dec 11 | Finalize the privacy policy and terms of service | Required before sign-up opens |

---

## Phase 1: Skeleton ✅

**Delivered:** Docker Compose (Postgres on port 55432, Redis on 6380); a FastAPI service with endpoints to create, fetch and list searches, list a search's posts, and check health; arq background jobs; the full schema with Alembic migrations; the `ChannelAdapter` and `SupplyAdapter` interfaces; a provider-agnostic LLM layer with per-task model routing and JSON validation with retry; and the collection pipeline itself, including depth-tier limits, 24-hour reuse of raw data, and isolation so one failing channel doesn't fail the search. 12 tests passing.

**Carried over:** user foreign keys are nullable for now and become required in phase 6.

---

## Phase 2: Collection (Reddit + TikTok)

**Goal:** given a real keyword, collect enough relevant posts and comments from Reddit and TikTok, and keep working when the platforms push back.

**Deliverables:**

*Reddit adapter.* Uses Reddit's official API. Search runs along two paths. One is a site-wide search sorted by relevance and limited to the past year. The other first identifies the subreddits most relevant to the keyword (for example, "camping chair" surfaces r/CampingGear and r/BuyItForLife) and searches within them. Results from both paths are merged and deduplicated. Comments are fetched sorted by top, and the number of "load more comments" expansions is capped so a single thread can't stall a whole search.

*TikTok adapter.* Supports keyword video search and comment collection, with a fallback path for comments if the primary one is unavailable. Video captions, view counts, likes and hashtags are kept in the `raw` field for later analysis.

*Resilience.* Every request retries with exponential backoff, a proxy pool can be plugged in through configuration, and each channel has a concurrency limit. Typical block signals (403s, captcha pages, expired credentials) are all converted into `ChannelError` so the layer above can degrade gracefully. The `/channels` endpoint reports the result of a real health probe.

*Progress streaming.* A new SSE endpoint, `GET /searches/{id}/events`, lets the frontend show live progress such as "Reddit: 12/20 posts collected, TikTok: fetching comments".

**Acceptance criteria:**
- Running the standard tier for "camping chair", "lick mat for dogs" and "cooler organizer" yields at least 15 relevant posts per channel and at least 2,000 comments in total, each within 8 minutes.
- In a manual spot check of 20 posts, at least 80% are relevant to the keyword.
- With the TikTok source unavailable or its credentials invalidated, the search still completes, and TikTok is flagged as failed in the result.
- Offline tests built on recorded real responses; CI never calls the live platforms.

**Needed from the owner:** Reddit and TikTok access credentials, filled into `.env`; a decision on whether to buy proxies now. The recommendation is to wait until we have measured how often we actually get blocked.

**Risks:** commercial use of Reddit's Data API requires a separate license. It's fine during the free test period but must be sorted out before charging. TikTok's anti-bot measures change quickly, and this adapter is expected to carry the highest maintenance cost in the system.

---

## Phase 3: Demand side + agent execution layer

**Goal:** turn thousands of comments into a demand report a seller can understand and trust, derive the opportunities that still need verifying, and build the controlled agent execution layer that phase 5 and later features run on.

**Deliverables:**

*Discovery (L1).* Before collection, one LLM call expands the keyword into closely related search terms and lists the subreddits and hashtags where the product is discussed. Collection adapters take this as input instead of the raw keyword.

*Cleaning.* Remove emoji-only comments, comments that only tag friends, very short comments (under three words), copy-paste spam and likely bots. Detect language and keep English only in v1. A lightweight LLM pass then drops comments that have nothing to do with the product. For example, under a dog video, a thread about the dog's breed is irrelevant to the lick mat being sold.

*Clustering.* Comments are embedded with a multilingual sentence-embedding model, running locally by default to keep costs down, and swappable for an API-based model, then grouped by topic clustering. The number of clusters isn't fixed; it is inferred from the data, and very small clusters are merged.

*Categorizing and naming.* For each cluster, the most-liked and most representative comments are sent to the LLM, which does five things: writes a title, writes a one-sentence summary, assigns the cluster to one of the four categories (complaints, delights, questions, workarounds), picks 3–5 verbatim quotes, and translates each quote into Chinese. Clusters that fit none of the four categories are dropped.

*Coverage check (L1).* After the first classification pass, collect unassigned comments and low-confidence assignments and ask the LLM whether they contain an important pattern the report missed. If so, create a candidate cluster and re-classify the affected comments once; otherwise record the residual size in the sampling note. At most one rework round per report.

*Heat score.* Heat is not a raw sum of likes. It is `count + Σ log(1 + likes)`, so a single joke comment with 100k likes can't push its whole cluster to the top.

*Two report levels.* The keyword-level aggregate report is generated when the search finishes. A per-post report is generated only the first time a user opens that post, then cached, so no credits are wasted on posts nobody looks at.

*Sampling note.* Every report states how many posts and comments were collected, how many survived cleaning, that comments are the platform's top-ranked ones rather than a random sample, and how much each channel contributed.

*Opportunity extraction.* The LLM reads the full report and proposes 3–8 opportunities. Each is phrased as a concrete product-variant hypothesis, such as "a beach chair rated for 150 kg+ that folds into a shoulder-carry", and lists the clusters that support it.

*Agent execution layer.* A single interface, `run(task, tools, budget, output_schema) -> AgentResult`, behind which the agent runtime lives. The runtime enforces hard budgets (default per verification job: 20 steps, 5 minutes, $0.20 of LLM spend, 10 searches, 20 pages); when a limit is hit, the agent is asked to submit what it has and the result is marked budget-terminated. Output is validated against the given schema before it is returned. Every step is written to `agent_runs` / `agent_steps` with tool, input, output, tokens, cost and duration, and cost statistics (mean, P95) can be queried per task type.

**Acceptance criteria:**
- For three keywords, build a gold set by hand-reading 300 comments and marking the main pain points. The generated report must cover at least four of the top five hand-labeled pain points.
- Every claim in the report links back to source comments.
- Real LLM cost per tier is recorded, with targets of under $0.50 for standard and under $1.50 for deep.
- Running the same data twice yields essentially the same top three clusters in each category (titles may be worded differently).
- Coverage check: when one hand-labeled pain point is deliberately removed from the first pass, the check recovers it in at least two of the three keywords.
- Agent layer: tests with a scripted fake model show every budget limit stops the run, budget-terminated runs still return schema-valid partial output, and every step appears in the step log with its cost.

**Owner decisions:** whether embeddings run locally (cheaper, but the server needs about 2 GB more memory) or through an API; whether report titles and translations should be entirely in Chinese.

---

## Phase 4: Frontend workbench

**Goal:** build the three-pane workbench so a seller can go from keyword all the way down to verbatim quotes.

**Deliverables:**
- Built with Next.js, TypeScript and Tailwind, with a Chinese UI.
- Left pane: search history, each entry showing keyword, tier, status and time. At the top, a search box with tier and channel selection that shows how many credits the search will cost.
- Middle pane: the list of posts and videos, filterable by channel, showing title, views and likes, and comment count, with a link out to the original post.
- Right pane: the report. The aggregate report is laid out by the four categories, each cluster shown as a card with its title, count and heat score, expandable to quotes and translations. A donut chart shows the share of each category, alongside the sampling note. Clicking a post in the middle pane switches the right pane to that post's own report.
- While a search runs, per-channel progress streams over SSE, and failed channels show the reason.
- After phase 5, the right pane gains an "Opportunities & verdicts" section.

**Acceptance criteria:** usable at phone width, where the three panes collapse into tabs; the full flow works end to end (submit, watch progress, read the aggregate report, drill into a post, jump to the original); empty, failed and partially-failed states each have their own UI.

**Owner decision:** whether to review a design mockup before implementation. An interactive prototype can be produced first.

---

## Phase 5: Supply-side verification agent + verdicts

**Goal:** give each verified opportunity a verdict of "nobody does it", "done poorly" or "done well", backed by structured competitor evidence, a computed confidence level and a margin estimate.

**Deliverables:**

*Which opportunities.* Only the top-ranked opportunities are verified: top 2 on Light, top 3 on Standard, top 5 on Deep. The rest are marked "not verified". A per-search supply-side budget caps the total.

*Amazon adapter.* Uses a dedicated Amazon data provider. It fetches price, rating and review count for the top 10 competitors, plus recurring themes in their negative reviews. Exposed to the agent as a tool, and the strongest source of evidence for whether a product is "done poorly".

*Verification agent (L2).* Runs on the phase 3 execution layer with the task "prove whether supply for this opportunity actually exists, and how good it is". Tools: web search, page fetch, the Amazon adapter, and a tool to record each piece of evidence. The agent chooses its own path across Amazon, TikTok Shop, Temu/AliExpress and the open web, changing keywords and following links when evidence is thin. 1688 sourcing prices come from the same loop as an estimated range flagged "needs manual review".

*Structured evidence.* The agent must finish by submitting evidence in the fixed schema from the design doc (existing solutions with platform, URL, price, verbatim evidence, source type and strength; market gap; sourcing price range). Its free-form reasoning is never shown in the UI.

*Verdict (L1).* A bounded LLM call reads the structured evidence and returns one of the three verdicts, citing specific competitor links and verbatim negative reviews.

*Computed confidence.* High, medium or low, computed from the evidence by the rules in the design doc, never self-reported by the model. Low-confidence verdicts are labeled in the report and queued for operator review.

*Margin estimate.* Gross margin = (suggested retail − sourcing cost − inbound freight − platform commission and FBA fees) ÷ suggested retail. Freight and fees start from per-category defaults, which sellers will later be able to override.

**Acceptance criteria:**
- Test on 5 products with known answers, including some with an obvious gap, some saturated markets, and some where competitors' negative reviews cluster around one issue. The system's verdict agrees with human judgment on at least 4 of them.
- Every verdict cites at least 3 competitors with links.
- Supply-side cost per opportunity stays under $0.30, data API fees included; the step log reports mean and P95 cost per verification over at least 30 runs.
- No verification run exceeds any budget limit; budget-terminated runs produce schema-valid evidence marked low confidence.

**Owner decisions:** which Amazon data provider to use. Default freight and fee assumptions also need to come from the owner's experience.

---

## Phase 6: Accounts, credits, launch readiness

**Goal:** the product can be opened to invited outside users, and the cost of every search is controlled and traceable.

**Deliverables:**

*Accounts.* Email sign-in with a one-time login link and no password. Authentication will use either a hosted auth service or a self-built implementation.

*Credits.* An append-only credit ledger table records every grant, charge and refund. Credits are charged when a search is submitted, refunded automatically if it fails, and discounted when it hits the 24-hour cache. Admins can grant credits manually.

*Cost accounting.* Every search records what it actually spent on LLM calls and data APIs, viewable in aggregate in an admin view. Pricing will be set from this data.

*Operator review queue (L3).* An admin view lists low-confidence verdicts with their evidence and step log. The operator can confirm, correct or retract a verdict; corrections are stored as evaluation data. Review never blocks a user's report.

*Rate limiting and abuse prevention.* Caps on concurrent searches per user and on searches per day; new users receive a small number of free credits on sign-up.

*Launch readiness.* Cloud deployment, error monitoring, structured logging, daily automated database backups, and first drafts of a privacy policy and terms of service.

**Acceptance criteria:** a new user can sign up, receive credits, run a search, see credits deducted and read the report, end to end; a deliberately failed search refunds its credits automatically; the admin view shows a cost breakdown for each search.

**Owner decisions:** hosted versus self-built authentication; hosting platform; the free credit grant for new users and final prices for each tier.

**Note:** before the product starts charging, each channel's data-source arrangement should be reviewed and upgraded where needed (phase 7).

---

## Phase 7: v2

These items will be prioritized based on feedback from the first users. The current plan includes:

- **Upgrade data sources.** Review and, where needed, replace each channel's data source. Because of the adapter layer, this only means writing a new adapter, with no changes upstream. This should happen before the product starts charging.
- **Instagram channel.**
- **Proper 1688 integration.** Image-based product search with real sourcing prices and minimum order quantities.
- **Stripe payments.** Both credit packs and subscriptions.
- **Follow-up questions on a report.** A seller can ask questions about a finished report (for example, "which weight ranges do the load-capacity complaints come from?"), answered by an agent over the already-collected data, under the same budget and logging rules.
- **Multi-provider agent runtime.** Once agent verification has proven its value, add a second runtime behind the same interface so the agent layer can switch providers like the fixed LLM tasks.
- **Other candidates.** Scheduled keyword monitoring (automatic weekly reruns that show how pain points shift over time), PDF export of reports, and European marketplaces (which require multilingual comments).
