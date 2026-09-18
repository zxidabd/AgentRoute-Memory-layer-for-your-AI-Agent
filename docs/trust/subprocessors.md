---
title: Subprocessor Directory
description: Authorized third-party infrastructure and sub-service providers used by MemoryBrain.
---

# Authorized Subprocessor Directory

*Last Updated: September 2026*

MemoryBrain engages the following third-party subprocessors to deliver platform hosting, authentication, payment processing, transactional communication, and compliance automation.

| Subprocessor | Purpose / Service Scope | Data Transferred | Processing Location | Corporate Entity & DPA |
|---|---|---|---|---|
| **Amazon Web Services (AWS)** | Cloud infrastructure, computing, PostgreSQL hosting, vector search, encrypted object storage | Encrypted memory statements, embeddings, API request logs | United States (us-east-1) *(EU eu-west-1 available on-demand)* | Amazon Web Services, Inc. (SCCs executed) |
| **Cloudflare** | Edge reverse proxy, CDN, DDoS protection, Web Application Firewall (WAF), TLS termination | IP addresses, request headers, transit payload metadata | Global Edge Network (Anycast) | Cloudflare, Inc. (SCCs executed) |
| **Clerk** | User identity, multi-factor authentication (MFA), session management, organization team membership | User emails, names, user IDs, workspace membership roles | United States | Clerk Inc. (SOC 2 Type II certified) |
| **Stripe** | B2B payment processing, invoice generation, subscription management | Customer billing contact, card tokens, billing address, usage meter totals | United States / Global | Stripe, Inc. (PCI DSS Level 1) |
| **Razorpay** | International & regional payment gateway, recurring card mandates | Customer billing contact, currency info, transaction IDs | India / Global | Razorpay Software Private Ltd. (PCI DSS) |
| **Vanta** | Continuous security monitoring, automated compliance evidence collection, auditor verification | Configuration metadata, audit trail integrity proofs, access control logs | United States | Vanta, Inc. (SOC 2 Type II certified) |
| **Mintlify** | Public developer documentation hosting and API reference rendering | Public documentation requests, anonymous reader metrics | Global Edge CDN | Mintlify Inc. (SOC 2 Type II certified) |
| **Resend** | Transactional email delivery for team invitations and security alerts | Recipient email address, invitation token links | United States | Resend, Inc. (GDPR compliant) |

---

### Subprocessor Notification Policy
To subscribe to email notifications for proposed subprocessor additions or modifications, contact security@memorybrain.ai. MemoryBrain provides a minimum 30-day notice period before onboarding any new subprocessor.
