# DESK × Weft: licence and distribution

This is an engineering reading of the licence, not legal advice.

## Ownership

Weft is Copyright © 2026 WeaveMind, Inc. and is published at https://github.com/WeaveMindAI/weft under the
**O'Saasy License Agreement**. It is not MIT, not Apache, and not an OSI-approved licence. DESK is MIT (see
`LICENSE`). "Weft", "WeaveMind" and "Tangle" are upstream's names; DESK uses them only to say what it integrates
with. Upstream's licence text grants no trademark rights and states no trademark policy.

## What the licence says (read at commit 61fdacd)

It is the MIT permission grant (use, copy, modify, merge, publish, distribute, sublicense, sell) with two
conditions:

1. The copyright notice and the permission notice go with every copy or substantial portion.
2. No licensee or downstream recipient may use the software, modified or not, to **directly compete with the
   licensor by offering it to third parties as a hosted, managed or SaaS product where the primary value of the
   service is the functionality of the software itself**.

Upstream's own plain-language summary (which it says carries no legal weight) reads this as: build products on it,
run it inside your company, ship it inside something you sell; do not offer Weft itself as a hosted service.

## What DESK does

| Activity | In this repository | Obligation |
|---|---|---|
| Uses a Weft install the user sets up | Yes | None beyond the user's own acceptance of upstream's licence |
| Contains Weft source or binaries | **No.** The pin is a commit hash; the harness is DESK's own code that links a checkout the user provides | None |
| Programs written in the Weft language (`integrations/weft/`) | Yes, DESK's own work | None |
| Modifies Weft | Only the optional two-line Windows shim, applied to a local scratch checkout and never redistributed | None while it stays local |

## What needs a decision before it happens

- **Shipping Weft with DESK** (an installer or image that bundles Weft's source or binaries): permitted by the
  grant; DESK must then include upstream's copyright notice and licence text with the bundle.
- **Shipping a modified Weft** (for example the Windows shim inside a bundle): same condition, and the
  modification should be stated.
- **Offering DESK as a hosted service** to third parties while Weft runs underneath: this is where clause 2
  matters. DESK's value is electronics engineering, not workflow orchestration, which points toward "permitted",
  but "primary value" and "directly compete" are judgement calls. **Get a legal review, or written confirmation
  from upstream (contact@weavemind.ai), before any hosted commercial offering.**
- **Licence drift**: the licence can change at a later upstream commit. Re-read `LICENSE` whenever the pin moves.
