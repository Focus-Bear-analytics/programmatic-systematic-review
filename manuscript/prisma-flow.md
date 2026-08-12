# PRISMA 2020 flow diagram

```mermaid
flowchart TD
    %% Identification
    A1["<b>Identification</b>"]:::hdr
    A2["Records identified (n = 14,253)<br/>• Database searching: n = 4,817<br/>• Citation snowballing: n = 9,141<br/>• Digital self-control–tools snowball: n = 295"]
    A3["Duplicate records removed<br/>(n = 1,676)"]
    A2 --> A3

    %% Screening
    B1["<b>Screening</b>"]:::hdr
    B2["Records screened on title/abstract<br/>(n = 12,577)"]
    B3["Records excluded by recall-safe<br/>dual-rater screening (n = 12,471)<br/>• Not autistic/ADHD population<br/>• Not a digital app-based intervention<br/>• Not adults / not empirical"]
    A3 --> B2
    B2 --> B3

    %% Eligibility
    C1["<b>Eligibility</b>"]:::hdr
    C2["Reports assessed for eligibility<br/>at full text (n = 106)<br/>(4 reports not retrievable;<br/>assessed on available data)"]
    C3["Reports excluded (n = 106), with reasons:<br/>• Not a co-occurring adult-AuDHD sample: n = 58<br/>• Off-target outcome (not attention/EF/<br/>&nbsp;&nbsp;emotional regulation): n = 17<br/>• Insufficient rigour (uncontrolled / N &lt; 20 /<br/>&nbsp;&nbsp;undetermined): n = 31"]
    B2 --> C2
    C2 --> C3

    %% Included
    D1["<b>Included</b>"]:::hdr
    D2["Studies included in review<br/>(n = 0)"]:::empty
    C2 --> D2

    classDef hdr fill:#1f3b57,color:#fff,font-weight:bold;
    classDef empty fill:#7a1f1f,color:#fff,font-weight:bold;
    class A1,B1,C1,D1 hdr;
```

## Numbers used (reproducible from the pipeline)

| Stage | n |
|---|---|
| Records identified (all sources) | 14,253 |
| — Database searching | 4,817 |
| — Citation snowballing | 9,141 |
| — DSCT snowball (seed doi:10.1145/3571810) | 295 |
| Duplicates removed | 1,676 |
| Records screened (title/abstract) | 12,577 |
| Excluded at screening (recall-safe dual-rater) | 12,471 |
| Full-text reports assessed for eligibility | 106 (78 main arms + 28 DSCT referred) |
| — not retrievable (assessed on available data) | 4 |
| Full-text excluded — wrong population (not adult AuDHD) | 58 |
| Full-text excluded — off-target outcome | 17 |
| Full-text excluded — insufficient rigour | 31 |
| **Studies included** | **0** |

**Notes.** Screening was performed with a recall-safe, dual-rater AI protocol (Nova 2 Lite + Claude Sonnet 4.6): a record was excluded only when both raters agreed on an explicitly excluding value; "unspecified" judgments and disagreements were referred onward. Full-text exclusion categories pool the candidate-level decisions in `fulltext_review_master.csv` with the resolved DSCT-snowball referrals (`dsct_resolved.csv`); the 28 DSCT full-text referrals all failed on population (non-neurodivergent or excluded modality) and are counted under "wrong population."
```
