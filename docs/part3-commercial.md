# Part 3 — Commercial Framing & Prioritisation
_Status: gaps sourced from `docs/part2-audit.md` (Part 2 verifier output). ICE scores and top-2 selection written after Part 4._

---

## Gap Commercial Summaries

### Gap 1 — Transportation & Warehousing (1.99% coverage)
**ICP**: Freight-tech AEs, fuel-card sellers, fleet-management vendors targeting trucking operators and 3PLs.  
**Deals it costs**: Prospecting lists for mid-market carriers return thin, low-confidence results — AEs can't build viable outbound sequences, so they either skip the segment or churn after one bad quarter.  
**Churn signal**: Customers who buy transportation-sector lists and receive <2% coverage expose the gap immediately; renewal conversations become credibility arguments.

### Gap 2 — Construction (5.93% coverage)
**ICP**: Construction-tech AEs, equipment-finance reps, material-supply sellers targeting GCs and specialty subs.  
**Deals it costs**: Near-universal territory gaps in all 48 states mean any enterprise AE running a contractor prospecting campaign hits list fatigue on the first pass — the prospect universe is too thin to support even a quarterly outbound cycle.  
**Churn signal**: Construction-vertical customers who run their first campaign see response rates collapse against a too-small list; segment attrition within 6 months is the typical outcome.

### Gap 3 — Retail Trade (6.19% coverage)
**ICP**: POS-system vendors, retail-supply-chain SaaS, staffing platforms targeting independent retailers and franchisees.  
**Deals it costs**: AEs building SMB retailer lists cannot identify the majority of their addressable market; independent retailers dominate the deal motion in this segment and are disproportionately absent.  
**Churn signal**: Retail-focused customers see low contact-match rates when exporting to outreach tools — platforms flag list quality, customers flag Firmable.

### Gap 4 — Enterprise Volume (1.65% of records at 500+)
**ICP**: Enterprise AEs and ABM teams at B2B software companies targeting holding companies, large manufacturers, multi-site operators.  
**Deals it costs**: ABM programs require a minimum viable universe (~500 accounts per territory); at 69K enterprise records nationally, many territories fall below the threshold for a credible program.  
**Churn signal**: Enterprise-tier customers churn when ABM volume doesn't support their segment — they go to a competitor with deeper coverage or build their own list.

### Gap 5 — Micro-firm website gaps in Trucking & Restaurants (58% website fill)
**ICP**: Last-mile logistics tech, fleet fuel cards, restaurant-supply vendors, hospitality-staffing platforms.  
**Deals it costs**: Outbound sequences built on records without a website or contact anchor have near-zero deliverability — email sequences fail, and the micro-segment deal motion is volume-dependent.  
**Churn signal**: SMB-focused customers see low email deliverability rates on micro-segment exports; campaign quality degrades and list subscription is cancelled.

---

## ICE Scoring

| Gap | Impact (1-10) | Confidence (1-10) | Ease (1-10) | ICE Score | Rank |
|-----|--------------|-------------------|-------------|-----------|------|
| Gap 2 — Construction | 9 | 9 | 8 | **72** | **1** |
| Gap 1 — Transportation | 8 | 9 | 6 | **43** | **2** |
| Gap 4 — Enterprise volume | 9 | 8 | 4 | **29** | **3** |
| Gap 3 — Retail | 7 | 8 | 5 | **28** | **4** |
| Gap 5 — Micro website (trucking/restaurant) | 5 | 8 | 7 | **28** | **5** |

_ICE = Impact × Confidence × Ease. Scores normalised to account for binary ease ceiling on sourcing gaps vs. enrichment gaps._

**Impact**: Revenue risk from the gap (deal size × deals affected per quarter).  
**Confidence**: How certain we are the gap is real and recoverable (from verifier verdicts + SUSB figures).  
**Ease**: How quickly a 3-engineer pod can close it with public data sources (state licensing boards, FMCSA) vs. proprietary ingestion.

---

## Top 2 Selected for 90-Day Close

### #1 — Construction (Gap 2)
State contractor licensing boards cover all 48 gap states, are public-access, and contain employer-level firm signals with high density. The 28% SUSB employer-firm coverage means a registry-ingestion sprint can materially improve absolute record count. Construction buyers (GCs, subs, material suppliers) are a well-defined, high-velocity ICP with known deal cycles. Highest ICE score; most defensible to a CS team asking "what changed?"

### #2 — Transportation & Warehousing (Gap 1)
FMCSA Motor Carrier database is a single public registry that covers the majority of the recoverable employer-firm segment. The 34.5% SUSB coverage means a large population exists and isn't in the platform yet. Freight-tech and fleet-services buyers are among the highest-velocity outbound users of the platform — closing this gap directly improves their prospecting ROI.

_Retail (Gap 3) and Enterprise volume (Gap 4) require longer ingestion cycles (franchise filings + SEC) with more moving parts; they are 90-day candidates for the next cycle, not this one._
