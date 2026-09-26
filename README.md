# Micro‑Influencer Discovery Engine — Mermaid Architecture Diagram

```mermaid
flowchart TD

    A[Social Platforms<br/>TikTok] --> B[Scraping Layer<br/>Playwright · Proxies · Device Spoofing]

    B --> C[Creator Extraction<br/>Stats · Posts · Hashtags · Frequency]

    C --> D[AI Enrichment Layer<br/>LLM · Embeddings · Vision · Fraud Detection]

    D --> E[Scoring Layer<br/>Quality Score · Hidden Gem Score · Niche Fit]

    E --> F[Clustering Layer<br/>Niche · Style · Audience]

    F --> G[Automation Layer<br/>Daily Discovery · Surfacing · Outreach]

    G --> H[CRM<br/>Creator Cards · Pipelines · Notes]
