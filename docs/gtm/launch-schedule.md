# MemoryBrain — Go-to-Market Launch Calendar & Milestone Schedule

This schedule details the 4-week execution timeline spanning private design-partner outreach, public Show HN, cool-down bug fixes, Product Hunt launch, and post-launch conversion reviews.

---

## Master Launch Timeline

```
Week 1 (Private Outreach)   ──────► Target 30 ICP founders (10 Support, 10 Dev, 10 Sales)
Week 2 (Partner Onboarding) ──────► 5–10 design partners live; collect quotes & latency metrics
Week 3, Tuesday (Show HN)   ──────► Show HN launch (08:00 AM ET); War Room active; developer feedback
Week 3, Wed–Fri (Cool-down) ──────► Address HN feedback; ship hotfixes; finalize PH gallery
Week 4, Tuesday (Prod Hunt) ──────► Product Hunt launch (12:01 AM PT); HUNTER90 promo; maker AMA
Week 4, Friday (Review)     ──────► Baseline metrics audit (signups, TTFM, free-to-paid conversion)
```

---

## Detailed Milestone Execution Breakdown

### Phase 1: Private ICP Outreach Wave (Days 1–10)
- **Goal:** Secure 5–10 active design partners on 90-day complimentary Growth tier.
- **Tasks:**
  - Execute personalized emails and LinkedIn messages using `docs/gtm/outreach-templates.md`.
  - Issue pre-provisioned API keys with 50,000 memory quotas.
  - Set up shared Slack/Discord channels for direct founder-to-developer support.
  - Collect at least 2 verified case studies and latency quotes (`docs/gtm/case-studies.md`).

### Phase 2: Pre-Launch Dry Run & Freeze (Days 11–13)
- **Goal:** Complete end-to-end rehearsal of entire public acquisition funnel.
- **Tasks:**
  - Execute automated dry-run script `python scripts/gtm_dry_run.py`.
  - Verify public links, documentation endpoints, and pricing consistency.
  - Confirm Better Uptime monitoring and synthetic checks on `/healthz/liveness`.
  - Freeze non-critical code changes 48 hours before Show HN.

### Phase 3: Public Show HN Launch Day (Day 14 / Tuesday, 08:00 AM ET)
- **Goal:** Front-page discussion on Hacker News focused on architecture, latency, and open SDKs.
- **Tasks:**
  - 08:00 AM ET: Submit Show HN post (`docs/gtm/show-hn-launch.md`).
  - 08:05 AM ET: Post technical maker comment detailing hybrid BM25 search and AES-256 encryption.
  - War room active: Maintain <15 minute response SLA on all comments.
  - Real-time SRE monitoring: Track Cloud Run scaling and read replica utilization.

### Phase 4: Cool-Down & Product Polish (Days 15–20)
- **Goal:** Turn HN technical feedback into immediate product improvements before business/product audience on PH.
- **Tasks:**
  - Ship any reported SDK papercuts or documentation clarifications.
  - Update `docs/quickstart.mdx` with common HN setup questions.
  - Finalize Product Hunt gallery assets and prepare maker comment.

### Phase 5: Product Hunt Launch Day (Day 21 / Tuesday, 12:01 AM PT)
- **Goal:** Top 3 Product of the Day; broad developer & product manager adoption.
- **Tasks:**
  - 12:01 AM PT: Publish Product Hunt listing (`docs/gtm/product-hunt-launch.md`).
  - Post opening maker comment with promo code `HUNTER90`.
  - Engage with global hunters across European, US, and Asian voting windows.
  - Provide live onboarding support in Discord.

### Phase 6: Funnel Review & Handoff to Step 7 (Day 25)
- **Goal:** Measure launch performance against baseline targets.
- **Metrics Evaluated via `/v1/analytics/gtm/baseline`:**
  - Total signups ($> 250$ target).
  - Activation rate ($> 40\%$ storing $\ge 1$ memory within 24h).
  - Median Time-to-First-Memory ($< 5\text{ minutes}$).
  - Free-to-Paid conversion ($> 3.5\%$ within 14 days).
