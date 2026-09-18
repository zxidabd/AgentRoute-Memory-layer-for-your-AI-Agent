# MemoryBrain — Financial Operations, Revenue Recognition (ASC 606) & Unit Economics

This standard operating procedure governs subscription revenue recognition, monthly financial close, sales-tax nexus compliance, and unit economics tracking.

---

## 1. SaaS Revenue Recognition (ASC 606 Compliance)

Under ASC 606, subscription revenue must be recognized **as the performance obligation is satisfied over time**, not when cash is collected.

### Key Rules:
1. **Monthly Subscriptions ($49/mo, $249/mo):**
   - Recognized pro-rata over the 30-day billing period.
   - Billed at period start via Stripe/Razorpay.
2. **Annual Enterprise Prepayments ($20,000+ upfront):**
   - Cash collected upfront is booked to **Deferred Revenue (Liability Account 2200)**.
   - Monthly amortization: Recognized revenue = $\text{Total Contract Value} / 12$ each month.
   - Example: A $24,000 annual contract pays upfront in January; recognize $2,000/month through December.
3. **Usage Overages ($0.10/1k queries, $1.00/1k memories):**
   - Billed in arrears at invoice period close.
   - Recognized immediately in the month the usage occurred.

---

## 2. Sales-Tax Nexus & Value Added Tax (VAT) Governance

- **United States:** Stripe Tax monitors economic nexus thresholds per state (typically $100,000 in sales or 200 separate transactions).
  - Once threshold is breached in a jurisdiction, register with the state department of revenue within 30 days.
- **European Union:** B2B reverse-charge mechanism applies.
  - EU business customers must provide valid VAT ID during checkout.
  - If valid VAT ID is present: 0% VAT charged (customer accounts for reverse charge).
  - If no VAT ID is provided: Standard member-state VAT rate applied via Stripe Tax.

---

## 3. Monthly Financial Close Checklist (Completed by Day 5 of Month)

| Step | Action Item | Verification Source |
|---|---|---|
| **1. Stripe Reconciliation** | Export Gross Charges, Refunds, and Processing Fees. | Stripe Dashboard $\rightarrow$ Financial Reports |
| **2. Razorpay Net Remittance** | Reconcile INR remittances converted to USD bank account. | Razorpay Settlements Ledger |
| **3. Deferred Revenue Schedule** | Amortize 1/12th of all active annual enterprise contracts. | Accounting Software (QuickBooks/Xero) |
| **4. Cloud Infrastructure COGS** | Record GCP Cloud Run, Cloud SQL, and Redis hosting expenses. | Google Cloud Billing Console |
| **5. Third-Party Software COGS** | Record Clerk, Vanta, Resend, and Better Uptime invoices. | Credit Card Statements |
| **6. Gross Margin Calculation** | Verify Gross Margin $\ge 80\%$ on core memory API. | Close Summary Spreadsheet |

---

## 4. Unit Economics & Gross Margin Benchmark Model

MemoryBrain targets an **$85\%+$ software gross margin** across self-serve and enterprise plans.

### Gross Margin Formula:
$$\text{Gross Margin \%} = \frac{\text{Gross Subscription \& Overage Revenue} - \text{Total Hosting \& Processing COGS}}{\text{Gross Revenue}} \times 100$$

### Baseline Cost per 1,000,000 Memory Recalls:
| Component | Cost per 1M Recalls | Notes |
|---|---|---|
| **Cloud Run Ingress & Compute** | $1.20 | Auto-scaled container CPU cycles (22ms duration) |
| **Cloud SQL Read Replica I/O** | $0.80 | Indexed B-Tree + vector cosine similarity search |
| **Redis Cache Lookups** | $0.20 | Hot LRU memory entity caching |
| **Payment Gateway Fees (2.9% + 30¢)** | $1.45 | Blended Stripe/Razorpay processing fee |
| **Total COGS per 1M Recalls** | **$3.65** | — |
| **Revenue Earned per 1M Recalls (Growth)** | **$98.00** | $0.10 per 1k overage / included quota price |
| **Unit Gross Margin** | **96.3%** | High-efficiency database architecture |
