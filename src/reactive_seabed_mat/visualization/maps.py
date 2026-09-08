"""Map and timeline figures.  Plotly, offline, no tile server and no token.

Every figure carries its provenance and its units in the title or the colour
bar, because a map that does not say what it is showing is worse than no map.

Three things are deliberately kept visually distinct:

* the **seabed** view, which shows the residual flux leaving the mat, in
  ug/m2/d, over the hotspot footprint;
* the **water** view, which shows the dissolved concentration in the overlying
  water, in ng/L;
* the **risk** view, which is an explicitly labelled, unitless comparison
  against the untreated case, not a regulatory assessment.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from ..config import RunConfig
from ..contracts import FieldState, GridSpec, MatTileState, SeabedSourceField
from ..units import from_si_areal_flux, from_si_aqueous_concentration

__all__ = [
    "SYNTHETIC_BANNER",
    "seabed_flux_map",
    "water_concentration_map",
    "risk_ratio_map",
    "mat_condition_map",
    "attenuation_timeline",
    "saturation_timeline",
    "comparison_bar",
]

SYNTHETIC_BANNER = (
    "SYNTHETIC DEMONSTRATION - hypothetical hotspot, assumed parameters, "
    "not a real site and not field validated"
)

#: Sequential scale for "how much is coming out": low is good.
_FLUX_SCALE = "Inferno"
#: Sequential scale for water concentration.
_WATER_SCALE = "Turbo"


def _axes_m(grid: GridSpec) -> tuple[np.ndarray, np.ndarray]:
    x = grid.origin_x_m + (np.arange(grid.nx) + 0.5) * grid.dx_m
    y = grid.origin_y_m + (np.arange(grid.ny) + 0.5) * grid.dy_m
    return x, y


def _tile_shapes(tiles: Sequence[MatTileState]) -> list[dict[str, Any]]:
    """Outline every tile, coloured by what is wrong with it."""
    shapes: list[dict[str, Any]] = []
    for tile in tiles:
        geometry = tile.geometry
        x0 = geometry.x_m - geometry.width_m / 2.0
        x1 = geometry.x_m + geometry.width_m / 2.0
        y0 = geometry.y_m - geometry.length_m / 2.0
        y1 = geometry.y_m + geometry.length_m / 2.0
        if tile.displaced or not tile.active:
            colour, dash = "#ff2d55", "dot"
        elif tile.integrity_index < 0.999:
            colour, dash = "#ff9f0a", "dash"
        elif tile.burial_depth_m > 0.0:
            colour, dash = "#5e5ce6", "dashdot"
        else:
            colour, dash = "#30d158", "solid"
        shapes.append(
            {
                "type": "rect",
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "line": {"color": colour, "width": 2, "dash": dash},
                "fillcolor": "rgba(0,0,0,0)",
                "layer": "above",
            }
        )
    return shapes


def _base_layout(title: str, subtitle: str, grid: GridSpec) -> dict[str, Any]:
    return {
        "title": {
            "text": f"{title}<br><sub>{subtitle}</sub>",
            "x": 0.01,
            "xanchor": "left",
        },
        "xaxis": {"title": "east (m)", "constrain": "domain"},
        "yaxis": {
            "title": "north (m)",
            "scaleanchor": "x",
            "scaleratio": 1.0,
        },
        "margin": {"l": 60, "r": 20, "t": 80, "b": 50},
        "template": "plotly_dark",
    }


def seabed_flux_map(
    grid: GridSpec,
    source: SeabedSourceField,
    element: str,
    *,
    tiles: Sequence[MatTileState] = (),
    title: str = "Residual flux leaving the seabed",
    unit: str = "ug/m2/d",
):
    """Where contaminant is still entering the water, and how much.

    This is the map that shows a locally failed tile: its cells jump back to the
    bare-sediment flux while its neighbours stay dark.
    """
    import plotly.graph_objects as go

    flux = np.asarray(source.flux_kg_per_m2_per_s[element], dtype=float)
    display = from_si_areal_flux(flux, unit)
    x, y = _axes_m(grid)

    figure = go.Figure(
        go.Heatmap(
            z=display,
            x=x,
            y=y,
            colorscale=_FLUX_SCALE,
            colorbar={"title": f"{element} flux<br>({unit})"},
            hovertemplate=(
                "east %{x:.0f} m<br>north %{y:.0f} m<br>"
                f"{element} flux %{{z:.3g}} {unit}<extra></extra>"
            ),
        )
    )
    layout = _base_layout(
        f"{title}: {element}",
        f"{SYNTHETIC_BANNER}. Areal flux into the overlying water.",
        grid,
    )
    layout["shapes"] = _tile_shapes(tiles)
    figure.update_layout(**layout)
    return figure


def water_concentration_map(
    grid: GridSpec,
    field_state: FieldState,
    element: str,
    *,
    tiles: Sequence[MatTileState] = (),
    title: str = "Dissolved concentration in the overlying water",
    unit: str = "ng/L",
    zmax: float | None = None,
):
    """The plume in the water column, in a unit an operator would recognise."""
    import plotly.graph_objects as go

    concentration = np.asarray(
        field_state.concentration_kg_per_m3[element], dtype=float
    )
    display = from_si_aqueous_concentration(concentration, unit)
    display = np.where(field_state.land_mask, np.nan, display)
    x, y = _axes_m(grid)

    figure = go.Figure(
        go.Heatmap(
            z=display,
            x=x,
            y=y,
            colorscale=_WATER_SCALE,
            zmin=0.0,
            zmax=zmax,
            colorbar={"title": f"{element}<br>({unit})"},
            hovertemplate=(
                "east %{x:.0f} m<br>north %{y:.0f} m<br>"
                f"{element} %{{z:.3g}} {unit}<extra></extra>"
            ),
        )
    )
    layout = _base_layout(
        f"{title}: {element}",
        f"{SYNTHETIC_BANNER}. Depth-averaged over the mixing layer; land is blank.",
        grid,
    )
    layout["shapes"] = _tile_shapes(tiles)
    figure.update_layout(**layout)
    return figure


def risk_ratio_map(
    grid: GridSpec,
    field_with_mat: FieldState,
    field_without_mat: FieldState,
    element: str,
    *,
    tiles: Sequence[MatTileState] = (),
    floor: float = 1e-18,
):
    """Treated concentration as a fraction of the untreated case.

    1.0 means the mat changed nothing there; 0.0 means it removed everything.
    This is a **model comparison**, not an environmental risk assessment: no
    compliance threshold is applied anywhere, because none has been established
    for this demonstrator.
    """
    import plotly.graph_objects as go

    treated = np.asarray(field_with_mat.concentration_kg_per_m3[element], dtype=float)
    untreated = np.asarray(
        field_without_mat.concentration_kg_per_m3[element], dtype=float
    )
    ratio = np.where(untreated > floor, treated / np.maximum(untreated, floor), np.nan)
    ratio = np.where(field_with_mat.land_mask, np.nan, ratio)
    x, y = _axes_m(grid)

    figure = go.Figure(
        go.Heatmap(
            z=ratio,
            x=x,
            y=y,
            colorscale="RdYlGn_r",
            zmin=0.0,
            zmax=1.0,
            colorbar={"title": "treated /<br>untreated"},
            hovertemplate=(
                "east %{x:.0f} m<br>north %{y:.0f} m<br>"
                "ratio %{z:.3f}<extra></extra>"
            ),
        )
    )
    layout = _base_layout(
        f"Remaining fraction of the untreated plume: {element}",
        "Model comparison under identical forcing. NOT a compliance assessment: "
        "no regulatory threshold is applied.",
        grid,
    )
    layout["shapes"] = _tile_shapes(tiles)
    figure.update_layout(**layout)
    return figure


def mat_condition_map(
    grid: GridSpec,
    source: SeabedSourceField,
    element: str,
    *,
    tiles: Sequence[MatTileState] = (),
):
    """Why each cell emits: covered, uncovered, damaged, displaced or leaking.

    Uses the component breakdown the coupling already produces, so the map
    cannot disagree with the physics.
    """
    import plotly.graph_objects as go

    components = source.components.get(element, {})
    cover = np.asarray(
        components.get("effective_cover", np.zeros((grid.ny, grid.nx))), dtype=float
    )
    x, y = _axes_m(grid)

    figure = go.Figure(
        go.Heatmap(
            z=cover,
            x=x,
            y=y,
            colorscale="Greens",
            zmin=0.0,
            zmax=1.0,
            colorbar={"title": "effective<br>cover"},
            hovertemplate=(
                "east %{x:.0f} m<br>north %{y:.0f} m<br>"
                "effective cover %{z:.2f}<extra></extra>"
            ),
        )
    )
    layout = _base_layout(
        "Effective reactive cover over the hotspot",
        "Green outline: intact tile. Amber dashed: locally damaged. "
        "Red dotted: displaced. Blue: buried. "
        "Effective cover already excludes edge leakage.",
        grid,
    )
    layout["shapes"] = _tile_shapes(tiles)
    figure.update_layout(**layout)
    return figure


# ---------------------------------------------------------------------------
# Timelines
# ---------------------------------------------------------------------------

def attenuation_timeline(timeline: Sequence[Any], elements: Sequence[str]):
    """Flux attenuation against time, per element, with the honest floor drawn."""
    import plotly.graph_objects as go

    figure = go.Figure()
    years = [point.elapsed_years for point in timeline]
    for element in elements:
        figure.add_trace(
            go.Scatter(
                x=years,
                y=[point.attenuation.get(element, np.nan) for point in timeline],
                mode="lines",
                name=f"{element} attenuation",
            )
        )
    figure.update_layout(
        title={
            "text": "Contaminant-flux attenuation<br>"
            "<sub>1 - J_out / J_bare. The plateau is the diffusive barrier that "
            "remains after the chemistry is exhausted, not a chemical effect.</sub>",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="years since deployment",
        yaxis_title="attenuation (dimensionless)",
        yaxis_range=[0.0, 1.02],
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 90, "b": 50},
    )
    return figure


def saturation_timeline(timeline: Sequence[Any], elements: Sequence[str]):
    """Active-media saturation against time, per element."""
    import plotly.graph_objects as go

    figure = go.Figure()
    years = [point.elapsed_years for point in timeline]
    for element in elements:
        figure.add_trace(
            go.Scatter(
                x=years,
                y=[point.saturation.get(element, np.nan) for point in timeline],
                mode="lines",
                name=f"{element} saturation",
            )
        )
    figure.update_layout(
        title={
            "text": "Active-media saturation<br>"
            "<sub>Sorbed mass as a fraction of the allocated operating capacity. "
            "Keratin parameters are literature-derated assumptions.</sub>",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="years since deployment",
        yaxis_title="saturation fraction",
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 90, "b": 50},
    )
    return figure


def comparison_bar(
    labels: Sequence[str],
    values: Mapping[str, Sequence[float]],
    *,
    title: str,
    yaxis_title: str,
    subtitle: str = SYNTHETIC_BANNER,
):
    """Grouped bars for a like-for-like comparison, for example mat versus none."""
    import plotly.graph_objects as go

    figure = go.Figure()
    for name, series in values.items():
        figure.add_trace(go.Bar(x=list(labels), y=list(series), name=name))
    figure.update_layout(
        title={"text": f"{title}<br><sub>{subtitle}</sub>", "x": 0.01, "xanchor": "left"},
        yaxis_title=yaxis_title,
        barmode="group",
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 90, "b": 50},
    )
    return figure
