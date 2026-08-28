# Vendored data

## ConstellationLines.csv

Stick-figure line data for the 88 IAU constellations, as lists of Bright Star
Catalogue (HR) numbers forming a polyline per constellation.

- Source: <https://github.com/MarcvdSluys/ConstellationLines>
- Licence: **CC BY 4.0** — see ATTRIBUTION.md
- Vendored rather than fetched at build time so the build is reproducible and
  the provenance is visible in the repo.

Chosen over the alternatives on licence grounds: HYG is CC BY-SA, whose
ShareAlike would propagate into the derived catalogue, and Stellarium's
`constellationship.fab` is GPL.
