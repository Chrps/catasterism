# Attribution and licensing

Three separate things are licensed here. See PLAN.md §10c.

| What | Licence |
| --- | --- |
| The code in this repository | **MIT** — see [LICENSE](LICENSE) |
| The derived star catalogue (the tile files) | **CC-BY-4.0** |
| The underlying Gaia data | ESA/Gaia/DPAC — acknowledgement required, below |

## Required Gaia acknowledgement

This is an obligation, not a courtesy, and it is rendered **in the application
UI** rather than only here — the data is the product.

> This work has made use of data from the European Space Agency (ESA) mission
> [Gaia](https://www.cosmos.esa.int/gaia), processed by the Gaia Data
> Processing and Analysis Consortium
> ([DPAC](https://www.cosmos.esa.int/web/gaia/dpac/consortium)). Funding for
> the DPAC has been provided by national institutions, in particular the
> institutions participating in the Gaia Multilateral Agreement.

Cite Gaia Collaboration et al. (2016) for the mission and Gaia Collaboration
et al. (2023, A&A 674 A1) for Data Release 3.

## Third-party catalogues

Credited as each is adopted; several arrive in Step 3.

| Catalogue | Used for | Step |
| --- | --- | --- |
| Bailer-Jones et al. (2021), AJ 161, 147 — VizieR `I/352` | Bayesian distances beyond ~2 kpc, where parallax is unreliable | 3 |
| El-Badry, Rix & Heintz (2021), MNRAS 506, 2269 | Resolved binaries, for distance coherence | 3 |
| Lindegren et al. (2021), A&A 649, A4 | Parallax zero-point correction | 3 |
| Hipparcos (ESA, 1997) | Bright stars Gaia saturates on | 3 |
| A DR3 open-cluster membership catalogue (TBD) | Cluster distance coherence | 3 |
| SIMBAD and VizieR, CDS Strasbourg | Live identification queries | 5 |

SIMBAD and VizieR are operated by CDS, Strasbourg, France. Their use requires
citing Wenger et al. (2000) and Ochsenbein et al. (2000) respectively.
