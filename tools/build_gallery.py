"""Build the committed gallery: one offline page, plus PNGs GitHub can render.

    python tools/build_gallery.py --out docs/gallery

The point is that someone can look at the output before deciding whether to run
anything. GitHub does not render HTML from a repository listing, so the gallery
ships twice: `index.html` is the full interactive page for local viewing, and
`README.md` embeds PNG previews that render in the browser on GitHub itself.

The PNGs are drawn with matplotlib rather than exported from Plotly, because
Plotly's static export needs kaleido and this repository does not depend on it.
They are previews. The HTML page and the per-scenario reports are the artefact.

**This takes about forty minutes**: six scenarios plus a three-policy
comparison, each running a multi-year reactive-layer timeline with the evidence
loop, then short 2-D plume windows at named mat states. That is the reason the
output is committed rather than generated on demand. Use `--max-years` to cap
the timelines or `--skip-comparison` to drop the slowest part.
"""

from __future__ import annotations

import argparse
import sys
import time
import hashlib
import gzip
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402
import numpy as np                                             # noqa: E402

from reactive_seabed_mat.config import config_hash             # noqa: E402
from reactive_seabed_mat.deployment import scale_table         # noqa: E402
from reactive_seabed_mat.scenarios import registry             # noqa: E402
from reactive_seabed_mat.scenarios.run import run_scenario     # noqa: E402
from reactive_seabed_mat.units import from_si_areal_flux       # noqa: E402
from reactive_seabed_mat.visualization import maps             # noqa: E402
from reactive_seabed_mat.visualization.report import figures_for_result  # noqa: E402

_SECONDS_PER_YEAR = 365.25 * 86400.0

_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
       background: #111418; color: #e6e6e6; }
main { max-width: 1150px; margin: 0 auto; padding: 32px 24px 96px; }
h1 { font-size: 2.0rem; margin-bottom: 4px; }
h2 { font-size: 1.4rem; margin-top: 56px; border-bottom: 2px solid #2c323a;
     padding-bottom: 8px; }
h3 { font-size: 1.05rem; margin-top: 28px; color: #b9c2cc; font-weight: 600; }
.banner { background: #3a2a12; border: 1px solid #7a5a22; color: #ffcf8a;
          padding: 14px 18px; border-radius: 8px; margin: 18px 0 28px; }
.caption { color: #9aa4b0; font-size: 0.92rem; margin: 4px 0 18px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 24px;
        font-size: 0.92rem; }
th, td { border: 1px solid #2c323a; padding: 7px 11px; text-align: left; }
th { background: #1a1f26; }
code { background: #1a1f26; padding: 1px 5px; border-radius: 4px; }
nav a { color: #7fb2ff; margin-right: 14px; }
footer { color: #7e8894; font-size: 0.86rem; border-top: 1px solid #2c323a;
         padding-top: 16px; margin-top: 56px; }
"""


def _png(figure_fn, path: Path, *, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = figure_fn()
    fig.suptitle(title, fontsize=10, color="#e6e6e6")
    fig.savefig(path, dpi=110, facecolor="#111418", bbox_inches="tight")
    plt.close(fig)


def _flux_png(result, path: Path) -> None:
    """The seabed residual flux map, with tile outlines coloured by fault."""
    if not result.windows:
        return
    window = result.windows[-1]
    grid = window.field_with_mat.grid
    element = result.config.elements[0]
    values = from_si_areal_flux(
        np.asarray(window.source_with_mat.flux_kg_per_m2_per_s[element]), "ug/m2/d"
    ).reshape(grid.ny, grid.nx)

    extent = [
        grid.origin_x_m,
        grid.origin_x_m + grid.nx * grid.dx_m,
        grid.origin_y_m,
        grid.origin_y_m + grid.ny * grid.dy_m,
    ]

    def draw():
        fig, ax = plt.subplots(figsize=(6.2, 5.0))
        fig.patch.set_facecolor("#111418")
        ax.set_facecolor("#111418")
        image = ax.imshow(
            values, origin="lower", extent=extent, cmap="inferno", aspect="equal"
        )
        for tile in window.tiles:
            geometry = tile.geometry
            if tile.displaced or not tile.active:
                colour, style = "#ff2d55", ":"
            elif tile.integrity_index < 0.999:
                colour, style = "#ff9f0a", "--"
            elif tile.burial_depth_m > 0.0:
                colour, style = "#5e5ce6", "-."
            else:
                colour, style = "#30d158", "-"
            ax.add_patch(
                plt.Rectangle(
                    (geometry.x_m, geometry.y_m),
                    geometry.width_m,
                    geometry.length_m,
                    fill=False,
                    edgecolor=colour,
                    linestyle=style,
                    linewidth=1.6,
                )
            )
        bar = fig.colorbar(image, ax=ax, shrink=0.85)
        bar.set_label(f"{element} residual flux (ug/m2/d)", color="#c8d0d8")
        bar.ax.tick_params(colors="#c8d0d8")
        for spine in ax.spines.values():
            spine.set_color("#2c323a")
        ax.tick_params(colors="#c8d0d8")
        ax.set_xlabel("east (m)", color="#c8d0d8")
        ax.set_ylabel("north (m)", color="#c8d0d8")
        return fig

    _png(
        draw,
        path,
        title=f"{result.config.scenario}: residual {element} flux at "
              f"{window.label}",
    )


def _timeline_png(result, path: Path) -> None:
    """Attenuation per element against the barrier-only floor.

    The shaded band between each element's curve and the dashed floor IS the
    sorbent's contribution. Plotting only the total would credit the chemistry
    with the geometry's work, and for copper the band is invisible because the
    contribution really is zero.
    """
    if not result.timeline:
        return
    elements = list(result.config.elements)
    years = [point.elapsed_years for point in result.timeline]
    colours = {"Pb": "#30d158", "Hg": "#0a84ff", "Cu": "#ff9f0a"}

    def draw():
        fig, (top, bottom) = plt.subplots(
            2, 1, figsize=(6.8, 5.2), sharex=True,
            gridspec_kw={"height_ratios": [3, 2]},
        )
        fig.patch.set_facecolor("#111418")
        for ax in (top, bottom):
            ax.set_facecolor("#111418")
            ax.grid(alpha=0.15, color="#5a6470")
            ax.tick_params(colors="#c8d0d8", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#2c323a")

        for element in elements:
            colour = colours.get(element, "#e6e6e6")
            total = [100.0 * p.attenuation.get(element, np.nan)
                     for p in result.timeline]
            barrier = [100.0 * p.barrier_attenuation.get(element, np.nan)
                       for p in result.timeline]
            top.plot(years, total, color=colour, lw=2, label=f"{element} total")
            top.plot(years, barrier, color=colour, lw=1, ls=":", alpha=0.8)
            top.fill_between(years, barrier, total, color=colour, alpha=0.18)
            bottom.plot(
                years,
                [100.0 * p.saturation.get(element, 0.0) for p in result.timeline],
                color=colour, lw=2, label=f"{element}",
            )

        top.set_ylabel("flux attenuation (%)", color="#c8d0d8", fontsize=9)
        all_values = [100.0 * p.attenuation[e] for p in result.timeline for e in elements]
        top.set_ylim(min(0.0, min(all_values) - 1), max(101.0, max(all_values) + 1))
        bottom.set_ylabel("media saturation (%)", color="#c8d0d8", fontsize=9)
        bottom.set_xlabel("years since deployment", color="#c8d0d8", fontsize=9)
        bottom.set_ylim(-2, 102)
        for ax in (top, bottom):
            legend = ax.legend(facecolor="#1a1f26", edgecolor="#2c323a", fontsize=7)
            for text in legend.get_texts():
                text.set_color("#c8d0d8")
        top.text(
            0.99, 0.03,
            "dotted = barrier only, no capacity left; shaded = sorbent contribution",
            transform=top.transAxes, ha="right", va="bottom",
            color="#9aa4b0", fontsize=6.5,
        )
        fig.tight_layout()
        return fig

    _png(draw, path, title=f"{result.config.scenario}: through time")


def _scale_png(rows, path: Path) -> None:
    """Area to cover, log scale. The figure that says area capping is not a plan."""
    names = [str(row["name"]).split(",")[0].replace("This demonstrator's", "this")
             for row in rows]
    areas = [float(row["area_km2"]) for row in rows]
    tonnes = [float(row["sorbent_tonnes"]) for row in rows]

    def draw():
        fig, ax = plt.subplots(figsize=(7.4, 3.8))
        fig.patch.set_facecolor("#111418")
        ax.set_facecolor("#111418")
        bars = ax.bar(range(len(names)), areas, color="#ff453a")
        ax.set_yscale("log")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=22, ha="right", fontsize=7.5)
        ax.set_ylabel("area to cover (km2, log scale)", color="#c8d0d8", fontsize=9)
        ax.grid(axis="y", alpha=0.15, color="#5a6470")
        ax.tick_params(colors="#c8d0d8", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#2c323a")
        for bar, mass in zip(bars, tonnes):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.25,
                f"{mass/1000:,.0f} kt" if mass >= 1000 else f"{mass:,.0f} t",
                ha="center", color="#c8d0d8", fontsize=7,
            )
        fig.tight_layout()
        return fig

    _png(draw, path, title="Keratin needed to cover it. Every euro value is an assumption.")


def _comparison_png(rows, path: Path, element: str) -> None:
    labels = [row["policy"].replace("_", " ") for row in rows]
    mass = [row["into_water_kg"] for row in rows]
    cost = [row["cost_eur"] / 1.0e6 for row in rows]

    def draw():
        fig, (left, right) = plt.subplots(1, 2, figsize=(8.6, 3.4))
        fig.patch.set_facecolor("#111418")
        for ax, values, label, colour in (
            (left, mass, f"{element} into the water (kg)", "#ff453a"),
            (right, cost, "assumed service cost (EUR millions)", "#5e5ce6"),
        ):
            ax.set_facecolor("#111418")
            ax.bar(labels, values, color=colour)
            ax.set_ylabel(label, color="#c8d0d8", fontsize=9)
            ax.tick_params(colors="#c8d0d8", labelsize=8)
            ax.grid(axis="y", alpha=0.15, color="#5a6470")
            for spine in ax.spines.values():
                spine.set_color("#2c323a")
        fig.tight_layout()
        return fig

    _png(draw, path, title="Same assumptions, three servicing policies")


def _fig_html(figure, *, include_js: bool) -> str:
    return figure.to_html(
        full_html=False,
        include_plotlyjs=("inline" if include_js else False),
        default_height="460px",
    )


def _cached_run(task):
    config, directory, fingerprint = task
    path = Path(directory) / (fingerprint + '-' + config_hash(config) + '.pkl.gz')
    if path.exists():
        return str(path)
    started = time.perf_counter()
    result = run_scenario(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wb') as handle:
        pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"computed {config.scenario}/{config.policy.kind} in {time.perf_counter()-started:.0f}s", flush=True)
    return str(path)


def _read_result(path):
    # Only files produced locally by this script are loaded.
    with gzip.open(path, 'rb') as handle:
        return pickle.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/gallery")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cache-dir", default=".revision_cache/gallery")
    parser.add_argument(
        "--max-years", type=float, default=6.0,
        help="cap every scenario at this many years, to bound the build time",
    )
    parser.add_argument(
        "--skip-comparison", action="store_true",
        help="skip the three-policy comparison, which is the slowest part",
    )
    args = parser.parse_args()

    out = Path(args.out)
    (out / "img").mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    summary_rows: list[str] = []
    first_figure = True
    started_all = time.perf_counter()
    configs = [replace(registry.build_scenario(name), duration_s=min(
        registry.build_scenario(name).duration_s, args.max_years * _SECONDS_PER_YEAR))
        for name in registry.list_scenarios()]
    base = next(c for c in configs if c.scenario == "progressive_saturation")
    variants = [registry.policy_variant(base, policy) for policy in registry.POLICIES] if not args.skip_comparison else []
    digest = hashlib.sha256()
    for source in sorted((REPO / 'src').rglob('*.py')):
        if source.name not in ('cli.py', 'results.py') and 'visualization' not in source.parts:
            digest.update(source.relative_to(REPO).as_posix().encode())
            digest.update(source.read_bytes())
    fingerprint = digest.hexdigest()[:16]
    unique = {config_hash(c): c for c in configs + variants}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        paths = list(pool.map(_cached_run, [(c, args.cache_dir, fingerprint) for c in unique.values()]))
    cached = dict(zip(unique, paths))
    (out / 'cache_manifest.json').write_text(__import__('json').dumps({
        'scientific_source_fingerprint': fingerprint,
        'runs': [{'scenario': c.scenario, 'policy': c.policy.kind, 'config_hash': h,
                  'cache_file': Path(cached[h]).name} for h, c in unique.items()]}, indent=2), encoding='utf-8')

    for name in registry.list_scenarios():
        config = registry.build_scenario(name)
        config = replace(
            config, duration_s=min(config.duration_s, args.max_years * _SECONDS_PER_YEAR)
        )
        letter = registry.scenario_letter(name)
        print(f"[{letter}] {name}: {config.duration_years:.1f} yr ...", flush=True)
        started = time.perf_counter()
        result = _read_result(cached[config_hash(config)])
        elapsed = time.perf_counter() - started

        _flux_png(result, out / "img" / f"{name}_flux.png")
        _timeline_png(result, out / "img" / f"{name}_timeline.png")

        element = config.elements[0]
        final = result.timeline[-1] if result.timeline else None
        ledger = result.mat_ledger.get(element)
        maintenance = result.maintenance
        summary_rows.append(
            "<tr>"
            f"<td>{letter}</td><td><code>{name}</code></td>"
            f"<td>{config.duration_years:.1f}</td>"
            f"<td>{(final.attenuation[element] * 100.0):.1f} %</td>"
            f"<td>{(final.saturation[element] * 100.0):.0f} %</td>"
            f"<td>{(final.mean_coverage * 100.0):.0f} %</td>"
            f"<td>{(ledger.retained_in_mat_kg if ledger else 0.0):.3g}</td>"
            f"<td>{len(maintenance.service_events) if maintenance else 0}</td>"
            "</tr>"
        )

        blocks.append(
            f'<h2 id="{name}">Scenario {letter}: {name}</h2>'
            f'<p class="caption">{registry.scenario_description(name)}<br>'
            f"Run in {elapsed:.0f} s, config hash <code>{config_hash(config)}</code>, "
            f"seed {config.seed}.</p>"
        )
        for caption, figure in figures_for_result(result):
            blocks.append(
                f"<h3>{caption}</h3>" + _fig_html(figure, include_js=first_figure)
            )
            first_figure = False
        print(f"     done in {elapsed:.0f} s", flush=True)

    comparison_rows: list[dict] = []
    if not args.skip_comparison:
        scenario = "progressive_saturation"
        base = replace(
            registry.build_scenario(scenario),
            duration_s=min(
                registry.build_scenario(scenario).duration_s,
                args.max_years * _SECONDS_PER_YEAR,
            ),
        )
        element = base.elements[0]
        for policy in registry.POLICIES:
            print(f"[compare] {policy} ...", flush=True)
            variant = registry.policy_variant(base, policy)
            result = _read_result(cached[config_hash(variant)])
            maintenance = result.maintenance
            into_water = result.hotspot_into_water_kg.get(element, 0.0)
            comparison_rows.append(
                {
                    "policy": policy,
                    "into_water_kg": float(into_water),
                    "cost_eur": (
                        maintenance.assumed_service_cost_eur if maintenance else 0.0
                    ),
                    "services": len(maintenance.service_events) if maintenance else 0,
                    "retained_kg": float(
                        result.mat_ledger[element].retained_in_mat_kg
                        + result.mat_ledger[element].retained_in_retrieved_media_kg
                        if element in result.mat_ledger
                        else 0.0
                    ),
                }
            )
        _comparison_png(comparison_rows, out / "img" / "policy_comparison.png", element)

    base_config = registry.build_scenario("fresh_mat")
    _scale_png(
        scale_table(
            sorbent_loading_kg_per_m2=base_config.mat.sorbent_loading_kg_per_m2,
            mat_material_eur_per_m2=base_config.costs.mat_material_eur_per_m2,
            demo_hotspot_area_m2=(
                base_config.hotspot.width_m * base_config.hotspot.length_m
            ),
        ),
        out / "img" / "deployment_scale.png",
    )

    comparison_table = "".join(
        "<tr>"
        f"<td><code>{row['policy']}</code></td>"
        f"<td>{row['into_water_kg']:.4g}</td>"
        f"<td>{row['retained_kg']:.4g}</td>"
        f"<td>{row['services']}</td>"
        f"<td>{row['cost_eur']:,.0f}</td>"
        "</tr>"
        for row in comparison_rows
    ) or "<tr><td colspan='5'>not built in this run</td></tr>"

    nav = " ".join(
        f'<a href="#{name}">{registry.scenario_letter(name)}</a>'
        for name in registry.list_scenarios()
    )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reactive seabed mat: all scenarios</title>
<style>{_STYLE}</style></head><body><main>

<h1>Selective reactive seabed mat</h1>
<p class="caption">Every scenario, every map, in one offline page. Generated by
<code>tools/build_gallery.py</code> in {time.perf_counter() - started_all:.0f} s.</p>

<div class="banner"><strong>{maps.SYNTHETIC_BANNER}.</strong><br>
Reactive caps and activated-carbon amendments are established practice and no
novelty is claimed for them. Keratin operating parameters are assumptions informed
by laboratory literature; the finished mat has not been calibrated in seawater.
No supplier has been contacted and no quotation exists. Whole-hotspot attenuation
includes uncovered area and bypass; see <code>docs/EVIDENCE_BASE.md</code>.</div>

<nav>Jump to scenario: {nav}</nav>

<h2>Summary</h2>
<table>
<tr><th></th><th>Scenario</th><th>Years</th><th>Final attenuation</th>
    <th>Saturation</th><th>Coverage</th><th>Active mat (kg)</th><th>Services</th></tr>
{"".join(summary_rows)}
</table>

<h2>Three servicing policies, identical assumptions</h2>
<p class="caption">Scenario B. Same seed, same forcing, same hotspot schedule,
same observation schedule. Only <code>PolicyConfig.kind</code> differs.</p>
<table>
<tr><th>Policy</th><th>Pb into the water (kg)</th><th>Pb retained (kg)</th>
    <th>Services</th><th>Assumed cost (EUR)</th></tr>
{comparison_table}
</table>
<p class="caption">Emission integrates the same whole-hotspot source for every
policy. Retained mass sums active and retrieved column inventories; its separate
control volume is documented in the manuscript. Sparse Pb/Hg chemistry limits
evidence-informed servicing. Cu has no observation channel. Every euro value
is an assumption and service costs exclude full lifecycle expenditure.</p>

{"".join(blocks)}

<footer>
<p><strong>Limitations.</strong> A conceptual research demonstrator, not a
field-validated remediation system. 1-D per tile, uniform seepage, no
bioturbation, no consolidation, no competition between Pb and Hg for sites, and
a sediment reservoir that never depletes. A keratin mat over anoxic sediment is
a plausible substrate for sulfate-reducing bacteria, so capping could increase
methylmercury production: a risk to test, not a benefit. Nothing here simulates
or recommends handling unexploded ordnance; the source is an abstract authorised
hotspot.</p>
<p>Full detail in <code>docs/LIMITATIONS.md</code>,
<code>docs/EVIDENCE_BASE.md</code>, <code>docs/ASSUMPTIONS.md</code>,
<code>docs/MATERIAL_KERATIN.md</code> and <code>docs/PRIOR_ART.md</code>.</p>
</footer>
</main></body></html>
"""
    (out / "index.html").write_text(document, encoding="utf-8")
    size_mb = (out / "index.html").stat().st_size / 1024 / 1024
    print(f"wrote {out / 'index.html'} ({size_mb:.1f} MB) "
          f"in {time.perf_counter() - started_all:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
