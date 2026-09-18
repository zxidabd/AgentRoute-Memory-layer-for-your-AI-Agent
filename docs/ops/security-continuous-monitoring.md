# MemoryBrain — Continuous Security Monitoring & Annual Pen-Test Governance

This policy operationalizes ongoing SOC 2 Type II compliance, continuous automated vulnerability scanning, vulnerability remediation SLAs, and third-party penetration testing.

---

## 1. Automated Compliance & Vulnerability Monitoring (Vanta / Drata)

MemoryBrain uses continuous compliance automation connected to GitHub, Google Cloud Platform, and Cloudflare.

### Weekly Security Review Cadence:
- **Owner:** Platform / Security Lead (or Founder)
- **Schedule:** Every Tuesday at 10:00 AM PT
- **Inspection Checklist:**
  1. Review automated alerts in Vanta / Drata compliance dashboard.
  2. Verify all new production Cloud Run revisions pass container vulnerability scanning (Artifact Registry).
  3. Verify GitHub Dependabot alerts and update vulnerable dependencies via PR.
  4. Ensure zero open high-risk infrastructure misconfigurations (e.g. public Cloud SQL IP without SSL).

---

## 2. Vulnerability Remediation SLAs

Any vulnerability detected via static analysis (SAST), container scanning, or external reports must be patched within these strict timeframes:

| Vulnerability Severity | CVSS v3 Score | Remediation SLA | Verification Requirement |
|---|---|---|---|
| **Critical** | **9.0 – 10.0** | **< 48 Hours** | Emergency hotfix, canary deployment, and CVE re-scan verification. |
| **High** | **7.0 – 8.9** | **< 7 Days** | Fix included in weekly release branch with regression test. |
| **Medium** | **4.0 – 6.9** | **< 30 Days** | Prioritized in standard bi-weekly sprint backlog. |
| **Low / Informational** | **0.1 – 3.9** | **< 90 Days** | Addressed during routine dependency upgrades. |

---

## 3. Annual Third-Party Penetration Testing Protocol

### Trigger Conditions:
1. Reaching the **12-month anniversary** of platform launch.
2. Closing an Enterprise contract that contractually stipulates an independent penetration test report.
3. Prior to the formal audit issuance of our **SOC 2 Type II report**.

### Penetration Test Scope:
- **External Web Applications:** `https://api.memorybrain.ai`, `https://docs.memorybrain.ai`, and Developer Dashboard.
- **API Endpoints:** Authentication, RBAC boundary testing, rate limiting, and SQL/Command injection resistance.
- **Tenant Isolation Verification:** Comprehensive grey-box testing attempting cross-tenant memory access, adversarial IDOR, and version tamper attempts on `memory_versions`.
- **Infrastructure & Cloud Run:** Cloudflare WAF bypass, VPC isolation, and Cloud SQL network security.

### Post-Test Remediation Workflow:
- Pen-test firm delivers draft report within 10 business days of testing completion.
- Engineering team remediates all Critical/High findings within the stated SLA.
- Pen-test firm conducts re-test and issues clean **Attestation of Pen Test** letter for enterprise customers and SOC 2 auditors.
