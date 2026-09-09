"""Self-contained offline HTML evidence export.

One file, no network, no CDN: the Plotly bundle is inlined once and every figure
after that reuses it.  A juror can open the file from a USB stick on a laptop
with no internet and see the same numbers the app shows.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..config import RunConfig, config_hash, config_to_dict
from ..deployment.priority import rank_candidates
from ..deployment.scale import scale_table
from ..reactive_layer.geotextile import DEFAULT_GEOTEXTILE
from ..scenarios.registry import scenario_description, scenario_letter
from ..units import from_si_areal_flux, from_si_aqueous_concentration
from . import context_maps, maps

__all__ = ["write_html_report", "figures_for_result"]


def _fig_html(figure, *, include_js: bool) -> str:
    return figure.to_html(
        full_html=False,
        include_plotlyjs=("inline" if include_js else False),
        default_height="480px",
    )


def figures_for_result(result) -> list[tuple[str, Any]]:
    """Every figure for one scenario result, in presentation order."""
    config: RunConfig = result.config
    elements = list(config.elements)
    primary = elements[0]
    figures: list[tuple[str, Any]] = []

    if result.timeline:
        figures.append(
            ("Attenuation through time", maps.attenuation_timeline(result.timeline, elements))
        )
        figures.append(
            ("Media saturation through time", maps.saturation_timeline(result.timeline, elements))
        )

    for window in result.windows:
        grid = window.field_with_mat.grid
        tiles = window.tiles
        figures.append(
            (
                f"Seabed residual flux at {window.label}",
                maps.seabed_flux_map(
                    grid, window.source_with_mat, primary, tiles=tiles
                ),
            )
        )
        figures.append(
            (
                f"Effective reactive cover at {window.label}",
                maps.mat_condition_map(
                    grid, window.source_with_mat, primary, tiles=tiles
                ),
            )
        )
        zmax = max(
            window.peak_concentration(primary, with_mat=False),
            window.peak_concentration(primary, with_mat=True),
        )
        zmax_display = from_si_aqueous_concentration(zmax, "ng/L") if zmax > 0 else None
        figures.append(
            (
                f"Water concentration WITHOUT the mat at {window.label}",
                maps.water_concentration_map(
                    grid,
                    window.field_without_mat,
                    primary,
                    tiles=(),
                    zmax=zmax_display,
                ),
            )
        )
        figures.append(
            (
                f"Water concentration WITH the mat at {window.label}",
                maps.water_concentration_map(
                    grid,
                    window.field_with_mat,
                    primary,
                    tiles=tiles,
                    zmax=zmax_display,
                ),
            )
        )
        figures.append(
            (
                f"Remaining fraction of the untreated plume at {window.label}",
                maps.risk_ratio_map(
                    grid,
                    window.field_with_mat,
                    window.field_without_mat,
                    primary,
                    tiles=tiles,
                ),
            )
        )

    # Three-dimensional views: the sandwich, the sorption front through the
    # core, and the plume given a height. They answer questions the plan views
    # structurally cannot.
    figures.append(
        (
            "Mat construction, through the thickness",
            context_maps.mat_structure_3d(
                core_thickness_m=config.mat.thickness_m,
                geotextile_thickness_m=DEFAULT_GEOTEXTILE.thickness_m,
            ),
        )
    )
    if result.final_tiles:
        try:
            figures.append(
                (
                    f"{primary} sorbed load through the core, per tile",
                    context_maps.layer_profile_3d(
                        result.final_tiles,
                        primary,
                        geotextile_thickness_m=DEFAULT_GEOTEXTILE.thickness_m,
                    ),
                )
            )
        except ValueError:
            # A run with no sorbed profile for this element: skip the figure
            # rather than invent one.
            pass
    if result.windows:
        window = result.windows[-1]
        figures.append(
            (
                f"{primary} plume as a surface at {window.label}",
                context_maps.plume_surface_3d(
                    window.field_with_mat.grid, window.field_with_mat, primary
                ),
            )
        )

    # Where the documented contamination is, and how much of it there is.
    figures.append(
        ("Documented dumping areas, for scale", context_maps.baltic_context_map())
    )
    figures.append(
        (
            "Which hectares: candidate pilot areas by receptor proximity",
            context_maps.pilot_priority_chart(rank_candidates()),
        )
    )
    figures.append(
        (
            "Area to cover, against what a mat can lay",
            context_maps.deployment_scale_bar(
                scale_table(
                    sorbent_loading_kg_per_m2=config.mat.sorbent_loading_kg_per_m2,
                    mat_material_eur_per_m2=config.costs.mat_material_eur_per_m2,
                    demo_hotspot_area_m2=(
                        config.hotspot.width_m * config.hotspot.length_m
                    ),
                )
            ),
        )
    )

    if result.windows:
        labels = [window.label for window in result.windows]
        figures.append(
            (
                "Mass entering the water over each window",
                maps.comparison_bar(
                    labels,
                    {
                        "no mat": [
                            window.ledger_without_mat[primary].released_from_sediment_kg
                            for window in result.windows
                        ],
                        "with mat": [
                            window.ledger_with_mat[primary].released_from_sediment_kg
                            for window in result.windows
                        ],
                    },
                    title=f"{primary} entering the water column, per plume window",
                    yaxis_title="kg per window",
                ),
            )
        )
    return figures


def _ledger_rows(result) -> str:
    rows = []
    for element, ledger in result.mat_ledger.items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(element)}</td>"
            f"<td>{ledger.released_from_sediment_kg:.6g}</td>"
            f"<td>{ledger.boundary_in_kg:.6g}</td>"
            f"<td>{ledger.retained_in_mat_kg:.6g}</td>"
            f"<td>{ledger.retained_in_retrieved_media_kg:.6g}</td>"
            f"<td>{ledger.boundary_out_kg:.6g}</td>"
            f"<td>{ledger.numerical_correction_kg:.3g}</td>"
            f"<td>{ledger.relative_imbalance:.3e}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _maintenance_section(result) -> str:
    """The recommendation log, or an honest statement that there is none."""
    maintenance = getattr(result, "maintenance", None)
    config: RunConfig = result.config
    if maintenance is None:
        return ""
    if config.policy.kind == "none":
        return (
            "<h2>Maintenance</h2><p class='caption'>This run is the "
            "<strong>no mat</strong> reference case, so there is nothing to "
            "maintain and no recommendation is made. It exists to give the "
            "other two policies something honest to be compared against.</p>"
        )

    counts: dict[str, int] = {}
    for recommendation in maintenance.recommendations:
        counts[recommendation.action.value] = (
            counts.get(recommendation.action.value, 0) + 1
        )
    tally = "".join(
        f"<tr><td>{html.escape(action)}</td><td>{count}</td></tr>"
        for action, count in sorted(counts.items(), key=lambda kv: -kv[1])
    )

    events = "".join(
        "<tr>"
        f"<td>{html.escape(str(event.time_utc)[:10])}</td>"
        f"<td>{html.escape(', '.join(event.tile_ids))}</td>"
        f"<td>{sum(event.retrieved_kg.values()):.4g}</td>"
        f"<td>{event.cost_eur:,.0f}</td>"
        f"<td>{html.escape(event.execution_mode)}</td>"
        "</tr>"
        for event in maintenance.service_events
    ) or (
        "<tr><td colspan='5'>No service event was accepted over this "
        "timeline.</td></tr>"
    )

    last = maintenance.recommendations[-1] if maintenance.recommendations else None
    policy_explanation = (
        "Replacement follows the configured fixed interval; observations do not control its timing."
        if config.policy.kind == "fixed" else
        "Saturation recommendations use the configured "
        f"<code>{html.escape(config.policy.saturation_decision_bound)}</code> interval bound, "
        "a stated risk posture. Recent severe physical damage can also support replacement. "
        "Chemical decisions use supported Pb/Hg channels; Cu has no monitoring channel."
    )
    latest = (
        f"<p class='caption'><strong>Most recent recommendation:</strong> "
        f"{html.escape(last.action.value)}. {html.escape(last.reason)}<br>"
        f"<em>{html.escape(last.uncertainty_note)}</em></p>"
        if last is not None
        else ""
    )

    return f"""
<h2>Maintenance under the <code>{html.escape(config.policy.kind)}</code> policy</h2>
<p class="caption">{policy_explanation}
{maintenance.n_observations:,} synthetic observation records were
generated; the controller saw only those whose <code>available_at_utc</code> had
passed, so a laboratory result in transit could not influence an earlier
decision.</p>
<table>
<tr><th>Recommended action</th><th>Times</th></tr>
{tally or "<tr><td colspan='2'>none</td></tr>"}
</table>
<table>
<tr><th>Service date</th><th>Tiles</th><th>Retrieved (kg)</th>
    <th>Assumed cost (EUR)</th><th>Execution mode</th></tr>
{events}
</table>
{latest}
<p class="caption">Every recommendation carries
<code>human_confirmation_required = True</code> and
<code>execution_mode = "simulation_only"</code>. Nothing in this demonstrator
actuates anything, and no euro figure is a quotation.</p>
"""


def _material_rows(config: RunConfig) -> str:
    rows = []
    loading = config.mat.sorbent_loading_kg_per_m2
    for medium in config.mat.media:
        capacity = loading * medium.allocation_fraction * medium.q_max_kg_per_kg
        rows.append(
            "<tr>"
            f"<td>{html.escape(medium.element)}</td>"
            f"<td>{medium.q_max_kg_per_kg * 1e3:.3g} mg/g</td>"
            f"<td>{medium.kd_m3_per_kg:.3g} m&sup3;/kg</td>"
            f"<td>{medium.allocation_fraction:.2f}</td>"
            f"<td>{capacity:.3e} kg/m&sup2;</td>"
            f"<td>{html.escape(medium.provenance)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
       background: #111418; color: #e6e6e6; }
main { max-width: 1100px; margin: 0 auto; padding: 32px 24px 96px; }
h1 { font-size: 1.9rem; margin-bottom: 4px; }
h2 { font-size: 1.25rem; margin-top: 40px; border-bottom: 1px solid #2c323a;
     padding-bottom: 6px; }
.banner { background: #3a2a12; border: 1px solid #7a5a22; color: #ffcf8a;
          padding: 12px 16px; border-radius: 8px; margin: 16px 0 28px; }
.caption { color: #9aa4b0; font-size: 0.9rem; margin: 4px 0 18px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 24px;
        font-size: 0.92rem; }
th, td { border: 1px solid #2c323a; padding: 6px 10px; text-align: left; }
th { background: #1a1f26; }
code { background: #1a1f26; padding: 1px 5px; border-radius: 4px; }
.figure { margin: 8px 0 28px; }
footer { color: #7e8894; font-size: 0.85rem; border-top: 1px solid #2c323a;
         padding-top: 16px; margin-top: 48px; }
"""


def write_html_report(result, path: str | Path) -> Path:
    """Write one self-contained HTML file for a scenario result."""
    config: RunConfig = result.config
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    figures = figures_for_result(result)
    blocks = []
    for index, (caption, figure) in enumerate(figures):
        blocks.append(
            f'<div class="figure"><h2>{html.escape(caption)}</h2>'
            + _fig_html(figure, include_js=(index == 0))
            + "</div>"
        )

    letter = scenario_letter(config.scenario)
    description = scenario_description(config.scenario)

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reactive seabed mat: scenario {letter} ({html.escape(config.scenario)})</title>
<style>{_STYLE}</style></head><body><main>

<h1>Selective reactive seabed mat</h1>
<p class="caption">Scenario {letter}: <strong>{html.escape(config.scenario)}</strong>
&mdash; run <code>{html.escape(config.run_id)}</code>,
config hash <code>{config_hash(config)}</code>, seed {config.seed}.</p>

<div class="banner"><strong>{maps.SYNTHETIC_BANNER}.</strong><br>
Reactive caps and carbon amendments are established practice; no novelty is
claimed for them. Every material parameter is a literature-derated assumption,
not a measurement of our material. No supplier has been contacted and no
quotation exists. See the limitations at the foot of this page.</div>

<p>{html.escape(description)}</p>

<h2>What was simulated</h2>
<table>
<tr><th>Mat timeline</th><td>{config.duration_years:.1f} years at
    {config.dt_s / 3600.0:.0f} h steps, {config.n_steps} steps</td></tr>
<tr><th>Plume windows</th><td>{len(result.windows)} window(s) of
    {config.plume.window_s / 86400.0:.1f} day(s) at
    {config.plume.dt_s:.0f} s steps, with the mat state held fixed</td></tr>
<tr><th>Mat</th><td>{config.mat.tiles_x}&times;{config.mat.tiles_y} tiles,
    {config.mat.thickness_m * 1000.0:.0f} mm thick,
    {config.mat.sorbent_loading_kg_per_m2:.2f} kg/m&sup2; of medium,
    {config.mat.coverage_fraction * 100.0:.0f}% design coverage</td></tr>
<tr><th>Hotspot</th><td>{config.hotspot.width_m:.0f}&times;{config.hotspot.length_m:.0f} m,
    seepage {config.hotspot.schedule[0].seepage_velocity_m_per_s:.2e} m/s</td></tr>
<tr><th>Engines</th><td>layer: {html.escape(config.layer_engine)};
    coastal: {html.escape(config.transport_engine)}</td></tr>
</table>

<h2>Reactive medium (keratin, literature-derated)</h2>
<table>
<tr><th>Element</th><th>q_max</th><th>Kd</th><th>allocation</th>
    <th>capacity per area</th><th>provenance</th></tr>
{_material_rows(config)}
</table>
<p class="caption">Published Pb capacities for keratin biofibres are 4 to 33 mg/g
in deionised water at pH 4. Modified human hair has a published laboratory Hg
capacity of 476.7 mg/g (Liang et al., 2023), but the seawater wool/feather core
has no validated capacity. Its Hg setting remains an operating assumption.
Full derivation and sources: <code>docs/MATERIAL_KERATIN.md</code>.</p>

<h2>Mat mass ledger, whole timeline</h2>
<table>
<tr><th>Element</th><th>released from sediment (kg)</th>
    <th>initial column inventory (kg)</th>
    <th>active mat (kg)</th><th>retrieved (kg)</th><th>column outflow (kg)</th><th>numerical correction (kg)</th>
    <th>relative imbalance</th></tr>
{_ledger_rows(result)}
</table>
<p class="caption">Initial column inventory plus sediment inflow equals active
and retrieved inventory, column outflow and numerical correction. The mat ledger
covers the whole simulated timeline. The water
ledgers below each plume window cover that window only. The two are never added
together, because the coastal model was not integrated for years.</p>

{_maintenance_section(result)}

{"".join(blocks)}

<footer>
<p><strong>Limitations.</strong> This is a conceptual research demonstrator, not
a field-validated remediation system. The physical model is 1-D per tile with
uniform seepage, no bioturbation, no consolidation, no competition between Pb
and Hg for sites, and a prescribed sediment reservoir that never depletes. A
keratin mat over anoxic sediment is a plausible substrate for sulfate-reducing
bacteria, so capping could increase methylmercury production: that is a risk this
project must test, not a benefit. Nothing here simulates or recommends handling
unexploded ordnance; the source is an abstract authorised hotspot.</p>
<p><strong>Offline by construction.</strong> The Plotly bundle is inlined in this
file, and every figure is a heatmap, line or bar rendered locally, so opening
this page makes no network request and needs no account or map tile server.
(The inlined bundle does contain tile-server URLs for Plotly's geographic map
trace types; none of those trace types is used here, so none is ever fetched.)</p>
<p>Full detail in <code>docs/LIMITATIONS.md</code>,
<code>docs/ASSUMPTIONS.md</code>, <code>docs/MATERIAL_KERATIN.md</code> and
<code>docs/PRIOR_ART.md</code>.</p>
</footer>
</main></body></html>
"""
    target.write_text(document, encoding="utf-8")
    return target
