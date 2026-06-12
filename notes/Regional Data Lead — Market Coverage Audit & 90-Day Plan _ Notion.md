Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

Youʼre almost there — sign up to start building in Notion today. 

Sign up or login 

## 🌏 — Regional Data Lead Market Cover Audit & 90-Da Plan age y 

## Technical & Strategic Assessment 

## Who should NOT continue: 

❌ If you're short on time for an assessment. 

❌ If you can't read the full page right now. 

❌ If you're seeking a traditional 9-to-5 role. 

❌ If you don't believe in leveraging AI tools for productivity. 

❌ If you've never shipped real work using Claude Code, Cursor, or an equivalent agentic IDE. 

❌ If you treat LLMs as a wrapper around prompts rather than a system that needs evals, traces, and version control. 

❌ If you separate "product strategy" from "hands-on data work" in your head — this role does both, every day. 

## Overview 

Audit a market, prove out a closure pipeline, and write a tight 90-day plan a 3-engineer pod can run from on day 1. 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

1/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

Firmable's competitive moat is data — the deepest, most localised company and people dataset in every market we operate in. ANZ is the benchmark. SEA is live but coverage parity is uneven, especially in markets where there's no clean equivalent of an ABN, public registries are fragmented, and the "obvious" enrichment vendors don't have meaningful coverage. 

For this assessment, you'll use the US slice of a public 17M-company dataset as a proxy for APAC. The dataset is ~25% US (~4.25M records), broken down by state. Your scope is the total US market, with states acting as the subregion cut — proxying APAC's country / sub-region shape. The problem shape (coverage by sub-region, attribute fill rate, entity messiness, the LLM-vs-rule split, the commercial framing) is the same. The approach doesn't change. 

This assessment is biased heavily toward doing. We'd rather see a working pipeline and a thin plan than a thick plan and slideware. 

## Our Operating Principles 

1. AI is the workflow, not a tool — agents do the heavy lifting; you direct, evaluate, elevate. 

2. Rules where rules win, LLMs where they don't — and you can defend the split. 

3. Commercial framing first — every gap, every roadmap item ties to a deal Sales would win or a churn signal CS would prevent. 

4. Continuous, not big-bang — pods ship every week, not every quarter. 

5. Observability from day 1 — traces, costs, latency, decisions logged from the first call. 

6. Build > talk — a working PoC beats a polished deck, every time. 

## The Challen ge 

## — Part 1 Scope & Baseline (light) 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

2/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

Your scope is the total US market — all ~4.25M US records — with states as the sub-region dimension you'll cut and analyse against. Treat the US-ascountry / states-as-sub-regions shape as the proxy for an APAC country with regional sub-markets. 

Use the BigPicture 17M Company Dataset, filter to US, and augment with any public source you want (registry data, scraped web sources, LinkedIn — your call, your judgment on what's defensible). 

At this scale (~4.25M records), you cannot audit by hand and you cannot cheaply LLM-pass everything. How you sample, stratify, and prioritise is itself part of the test. 

Deliver a compact baseline: 

- Record counts, distributions, missingness, quality, candidate keys — nationwide and broken down by state. 

- A short note on which quality issues you'd attack with deterministic rules vs. LLMs, and why. We want to see you reach for rules first when rules are the right tool. 

- Your sampling and stratification strategy — how you'll get a defensible read on a 4M+ record dataset without burning weeks or thousands of dollars in tokens. 

- A clear statement of what "coverage parity" would mean across the US market — what attributes, at what fill rate, at what accuracy, and how that varies by state. 

Keep this part tight. It's setup, not the main event. 

## — Part 2 Agentic Coverage & Quality Audit 

Audit the dataset using agents, not by hand. We want to see you direct AI to do the legwork. 

Deliver: 

- A reusable agentic audit pipeline that scores coverage and quality across the dataset and surfaces structural gaps by industry, sub-region, company size, and any other dimension you find load-bearing. 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

3/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

- Clear separation of what the agents found vs. what you spot-checked. Trust calibration matters here — over-trusting the agent is a fail signal; under-trusting it (and re-doing everything by hand) is also a fail signal. 

- A ranked list of the top 5 structural gaps in this market. 

- For each gap, a short note: what's missing, how prevalent, how confident you are. 

You must show traces. Every agent call logged with prompt version, model, latency, cost, and outcome. JSONL or SQLite is fine. 

## — Part 3 Commercial Framing (tight) 

For each top gap, frame it commercially in a few sentences, not a page. Which customer (ICP, persona, deal size) feels this gap? Which deals does it cost? Which churn signals does it amplify? 

Then: 

- Prioritise the 5 gaps using a stated framework (RICE, ICE, your own — but stated and applied, not vibes). 

- Pick the top 2 to close in the next 90 days, with the reasoning made explicit. 

Compact beats comprehensive here. Reason from public market knowledge plus the data — no synthetic pack required. 

## — Part 4 Build the PoC Enrichment Pipeline (this is the main event) 

Pick one of your top 2 gaps. Build a working agentic enrichment pipeline that closes it for a real batch (target: 200–1000 records). 

The pipeline must include: 

- An agentic extraction/inference flow with explicit model choice per step (e.g. Haiku for cheap classification, Sonnet for nuanced judgement, frontier model for the hardest edge cases). Defend the choices. 

- Structured outputs with confidence scores per record. 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

4/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

- Retries, fallbacks, and cost controls — what happens when the model is uncertain, when a source is missing, when you're about to blow the cost ceiling. 

- A clear rule layer in front of the LLM, doing what rules do best. 

- A lightweight eval: hand-label 20+ records, run precision/recall on the output, report one number and one paragraph on where it's weak. We don't need a full eval harness — we need proof you'd never ship an LLM pipeline blind. 

Produce the enriched batch (200–1000 records) as a deliverable file. We'll spotcheck it. 

Spend most of your time here. This is what the role does on a good day. 

## — Part 5 Reusable Skill 

At Firmable, recurring AI workflows are packaged as skills — markdown specifications that any team member or agent can invoke to perform a defined task with defined inputs and outputs. A skill is a self-contained, versioned capability that lives in a repo and can be loaded by Claude Code, Cursor, or the API. 

Build at least one skill as part of this submission: 

- A `SKILL.md` for `coverage-audit` or the enrichment pipeline you built — your call which is more reusable. 

- The skill must describe: when to trigger it, required inputs, expected outputs, how to interpret the result, and known limitations. 

- Include a worked example invocation and the resulting output. 

Bonus points if your skill is genuinely something the rest of the data team could pick up and run on a different market without modification. 

## — Part 6 The 90-Day Pod Plan (tight) 

You've audited, framed, and proven out one closure. Now write the plan a 3- engineer pod will run from. 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

5/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

Keep this short and operational — aim for 1–2 pages, not 5. We're hiring someone who'd write a plan their team can pick up tomorrow, not a 10-page strategy deck. 

## Cover: 

- Thesis — one paragraph. What's the bet, why now, what does success look like. 

- Measurable outcomes — 3 concrete metrics with starting values (from your audit) and target values at day 90. 

- Work plan — 6–8 well-scoped, agent-augmented work items that look like Linear tickets a senior engineer could pick up tomorrow. Include rough effort sizing and dependencies. 

- Sequencing — a 30 / 60 / 90 day view with a go/no-go gate at day 30: what we'd need to see to keep going, kill, or pivot. 

- One risk and one bet — what could break this plan, and the one thing you'd protect if budget got cut in half. 

## Deliverables 

## GitHub Repository: 

- Code: agentic audit pipeline, PoC enrichment pipeline, traces. 

- `skills/` directory with your `SKILL.md` file(s). 

- `prompts/` directory with versioned prompts. 

- `data/` directory with the enriched output sample (200–1000 records). 

- `evals/` directory with your small labelled set and result. 

- `README.md` with setup, run, and reproduction instructions. 

## Notion Document (kept short): 

- US scope summary, sampling strategy, and rule-vs-LLM split (Part 1). 

- Agentic audit findings — top 5 gaps (Part 2). 

- Commercial framing and prioritisation (Part 3). 

- PoC enrichment pipeline walkthrough (Part 4). 

- Skill description and example invocation (Part 5). 

- The 90-day pod plan (Part 6) — front-and-centre, but tight. 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

6/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

- IDE(s) / agentic tools used. 

## Loom (≤7 minutes, strongly encouraged): 

A short walkthrough of your agentic dev loop and the system running end-toend. This is the easiest way for us to assess how you work, not just what you produced. Candidates who skip this are at a disadvantage — not because we'll penalise it, but because the written submission can't show us how you actually direct agents in real time. 

## Scope Guidance 

We bias hard toward building. If you have to cut, here's the priority order: 

1. Part 4 (PoC Pipeline) — the main event. Don't compromise this. 

2. Part 6 (90-Day Plan) — keep it tight. 

3. Part 2 (Agentic Audit) — reusable, traced. 

4. Part 3 (Commercial framing) — short. 

5. Part 5 (Reusable Skill) — are you in Apr 2026? 

Spend more time building than writing. A thin Notion doc backed by a strong PoC beats a thick Notion doc backed by a half-built pipeline, every time. 

## Notes 

- Iterate and fail fast. 

- Quality over quantity. A focused submission beats a sprawling one every time. 

- Ask questions if needed — but ask the right questions; we'll judge those too. 

- Use whatever models, tools, and infrastructure you want. We don't care if you ran it on your laptop, in a Modal sandbox, or on AWS. We care about the work. 

## Submission 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

7/8 

Regional Data Lead — Market Coverage Audit & 90-Day Plan | Notion 

11/06/2026, 11:43 

Share your GitHub repository link, Notion doc link, and Loom (if recorded) within 7 days of starting 

https://app.notion.com/p/firmable/Regional-Data-Lead-Market-Coverage-Audit-90-Day-Plan-353d5c6ffd878177bb4cd449480d5614 

8/8 

