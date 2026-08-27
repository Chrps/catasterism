# Attribution and licensing

Three separately-licensed things live in this project. See PLAN.md §10c.

| What | Licence |
| --- | --- |
| The code in this repository | **MIT** — see [LICENSE](LICENSE) |
| The derived star catalogue (tile files, and the T0 set in this repo) | **CC BY-NC 4.0** — it cannot be more permissive than its source, below |
| The underlying Gaia data | **CC BY-NC 3.0 IGO** (ESA/Gaia/DPAC) |

## The NonCommercial term is real

Gaia data are distributed under
[CC BY-NC 3.0 IGO](https://www.cosmos.esa.int/web/gaia-users/license). ESA's
[terms for the science archives](https://www.cosmos.esa.int/web/esdc/terms-and-conditions)
are explicit:

> Prior to any commercial use by the User of any Data or Data Product, including
> any use or application that **directly or indirectly generates a financial
> gain**, a detailed request for authorisation/licence shall be made by the User
> by sending email to data.licences@esa.int.

Practical consequences for this project:

- **No advertising, no paid tier, no sponsorship, no selling the tiles.**
  "Indirectly generates a financial gain" is broad; assume it covers ads and
  donation-for-access models.
- **The derived catalogue stays NonCommercial.** We cannot grant rights we were
  not given, so the tiles are CC BY-NC 4.0 rather than CC BY 4.0.
- **Do not imply ESA endorsement.** The terms forbid using the data to suggest
  ESA endorses a product, service or activity.
- **Open-sourcing is *not* required.** The licence obliges attribution and
  non-commercial use. It does not oblige publishing the code. This repository is
  public by choice.

If this ever becomes commercial, that is a written-permission conversation with
data.licences@esa.int before anything ships — not an afterthought.

*Not legal advice. The reading above is ours; ESA is the authority.*

## Required Gaia acknowledgement

An obligation, not a courtesy — and it is rendered **in the application UI**,
not only here, because the data is the product.

> This work has made use of data from the European Space Agency (ESA) mission
> [Gaia](https://www.cosmos.esa.int/gaia), processed by the Gaia Data
> Processing and Analysis Consortium
> ([DPAC](https://www.cosmos.esa.int/web/gaia/dpac/consortium)). Funding for
> the DPAC has been provided by national institutions, in particular the
> institutions participating in the Gaia Multilateral Agreement.

Cite Gaia Collaboration et al. (2016) for the mission and Gaia Collaboration
et al. (2023, A&A 674 A1) for Data Release 3.

## Third-party catalogues

Credited as each is adopted; several arrive in Step 3. **Check each one's own
licence before redistributing its values in the tiles** — they are not all
covered by the Gaia terms.

| Catalogue | Used for | Step |
| --- | --- | --- |
| Bailer-Jones et al. (2021), AJ 161, 147 — VizieR `I/352` | Bayesian distances beyond ~2 kpc, where parallax is unreliable | 3 |
| El-Badry, Rix & Heintz (2021), MNRAS 506, 2269 | Resolved binaries, for distance coherence | 3 |
| Lindegren et al. (2021), A&A 649, A4 | Parallax zero-point correction | 3 |
| Hipparcos (ESA, 1997) | Bright stars Gaia saturates on | 3 |
| A DR3 open-cluster membership catalogue (TBD) | Cluster distance coherence | 3 |
| SIMBAD and VizieR, CDS Strasbourg | Live identification queries | 5 |

SIMBAD and VizieR are operated by CDS, Strasbourg, France; their use requires
citing Wenger et al. (2000) and Ochsenbein et al. (2000) respectively. Both are
queried live from the browser, so be a considerate client — cache aggressively
and do not hammer them.
