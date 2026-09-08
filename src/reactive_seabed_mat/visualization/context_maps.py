"""Geographic context, deployment scale, and three-dimensional views.

Three kinds of figure that the flat seabed maps in ``maps.py`` cannot carry:

* **where** the documented contamination is, on a real map of the Baltic;
* **how much** of it there is, against what a mat can plausibly cover;
* **what the mat looks like through its thickness**, which is the whole point of
  a geotextile / reactive core / geotextile sandwich and is invisible in plan.

The geographic figure uses a plain scatter on a coastline outline rather than a
tiled basemap, so it stays offline and needs no tile server or token. The
dumpsite positions are approximate published centres, plotted to show scale.
**Nothing here proposes a deployment, and nothing here simulates, locates or
recommends handling munitions.**
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from ..deployment.scale import BALTIC_DUMPSITES, SCALE_NOTE, DumpSite
from .maps import SYNTHETIC_BANNER

__all__ = [
    "baltic_context_map",
    "deployment_scale_bar",
    "layer_profile_3d",
    "plume_surface_3d",
    "mat_structure_3d",
]

_DARK = "plotly_dark"

#: A very coarse Baltic and North Sea coastline, as closed rings of
#: (lon, lat).  Drawn only to give the dumpsite markers somewhere to sit; it is
#: a schematic outline, not a survey product, and it is labelled as one.
_BALTIC_OUTLINE: tuple[tuple[tuple[float, float], ...], ...] = (
    (
        (9.5, 54.8), (10.5, 54.4), (12.0, 54.2), (14.3, 53.9), (16.5, 54.5),
        (18.6, 54.6), (19.6, 54.4), (21.0, 55.3), (21.1, 56.1), (21.7, 57.6),
        (24.0, 57.8), (24.4, 59.5), (26.5, 60.0), (28.5, 60.2), (30.2, 59.9),
        (28.0, 59.5), (26.0, 59.6), (24.0, 59.4), (23.0, 60.0), (21.5, 61.0),
        (21.0, 63.0), (22.5, 65.5), (24.2, 65.8), (21.5, 63.5), (19.0, 62.0),
        (17.5, 60.5), (18.5, 59.3), (17.0, 58.7), (16.5, 57.0), (14.5, 55.4),
        (13.0, 55.4), (12.5, 56.2), (11.0, 57.5), (10.5, 56.0), (9.7, 55.0),
        (9.5, 54.8),
    ),
    (
        (7.0, 57.9), (9.0, 58.2), (10.5, 59.0), (11.2, 58.9), (10.8, 57.7),
        (9.5, 57.2), (8.2, 56.7), (7.0, 57.9),
    ),
)


def _outline_traces() -> list[dict[str, Any]]:
    traces = []
    for index, ring in enumerate(_BALTIC_OUTLINE):
        lon = [point[0] for point in ring]
        lat = [point[1] for point in ring]
        traces.append(
            {
                "type": "scatter",
                "x": lon,
                "y": lat,
                "mode": "lines",
                "line": {"color": "#4a5560", "width": 1.4},
                "fill": "toself",
                "fillcolor": "rgba(30, 58, 90, 0.35)",
                "name": "sea area (schematic)",
                "hoverinfo": "skip",
                "showlegend": index == 0,
            }
        )
    return traces


def baltic_context_map(
    sites: Sequence[DumpSite] = BALTIC_DUMPSITES,
    *,
    title: str = "Documented munitions dumping areas, and the scale of a mat",
):
    """Where the documented contamination is, with marker area set by site area.

    The point of the figure is the comparison a table cannot make: the marker
    for a designated dumpsite against the marker for anything a capping project
    could realistically lay.
    """
    import plotly.graph_objects as go

    figure = go.Figure()
    for trace in _outline_traces():
        figure.add_trace(go.Scatter(**trace))

    areas = np.array([site.area_km2 for site in sites], dtype=float)
    # Marker area proportional to site area, so the visual comparison is honest;
    # sqrt because Plotly sizes markers by diameter.
    sizes = 12.0 + 46.0 * np.sqrt(areas / areas.max())

    figure.add_trace(
        go.Scatter(
            x=[site.longitude_deg for site in sites],
            y=[site.latitude_deg for site in sites],
            mode="markers+text",
            marker={
                "size": sizes,
                "color": "#ff453a",
                "opacity": 0.55,
                "line": {"color": "#ff9f0a", "width": 1.5},
            },
            text=[site.name.split(",")[0] for site in sites],
            textposition="top center",
            textfont={"size": 10, "color": "#e6e6e6"},
            customdata=np.stack(
                [
                    areas,
                    [site.typical_depth_m for site in sites],
                    [
                        site.munitions_tonnes if site.munitions_tonnes else float("nan")
                        for site in sites
                    ],
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{text}</b><br>area %{customdata[0]:.0f} km2"
                "<br>typical depth %{customdata[1]:.0f} m"
                "<br>munitions %{customdata[2]:,.0f} t<extra></extra>"
            ),
            name="designated dumping area",
        )
    )

    figure.update_layout(
        title={
            "text": (
                f"{title}<br><sub>{SCALE_NOTE} Coastline is a schematic "
                "outline, not a survey product.</sub>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis={"title": "longitude (deg E)", "range": [6.0, 31.0]},
        yaxis={
            "title": "latitude (deg N)",
            "range": [53.0, 66.5],
            "scaleanchor": "x",
            "scaleratio": 1.7,
        },
        template=_DARK,
        margin={"l": 60, "r": 20, "t": 96, "b": 50},
        showlegend=False,
    )
    return figure


def deployment_scale_bar(rows: Sequence[Mapping[str, Any]]):
    """Area to cover, on a log scale, against what a mat project could lay.

    A log axis because a linear one would render the demonstrator's hotspot as
    a line of zero height next to a designated dumpsite, which is true but
    unreadable.
    """
    import plotly.graph_objects as go

    names = [str(row["name"]).split(",")[0] for row in rows]
    areas = [float(row["area_km2"]) for row in rows]
    tonnes = [float(row["sorbent_tonnes"]) for row in rows]
    euros = [float(row["mat_material_eur"]) for row in rows]

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=names,
            y=areas,
            marker_color="#ff453a",
            customdata=np.stack([tonnes, euros], axis=-1),
            hovertemplate=(
                "<b>%{x}</b><br>%{y:.4f} km2"
                "<br>%{customdata[0]:,.0f} t of sorbent"
                "<br>EUR %{customdata[1]:,.0f} of mat material<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title={
            "text": (
                "Area to cover, log scale"
                "<br><sub>Every euro value is an assumption. No supplier has "
                "been contacted. " + SCALE_NOTE + "</sub>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        yaxis={"title": "area (km2)", "type": "log"},
        template=_DARK,
        margin={"l": 70, "r": 20, "t": 100, "b": 110},
    )
    return figure


def mat_structure_3d(
    *,
    core_thickness_m: float,
    geotextile_thickness_m: float,
    tile_width_m: float = 1.0,
    tile_length_m: float = 1.0,
):
    """The sandwich, drawn: geotextile, reactive core, geotextile.

    Vertical scale is exaggerated by construction, and the figure says so,
    because a 3 mm layer over a 27 m tile is otherwise a line.
    """
    import plotly.graph_objects as go

    layers = [
        ("lower carrier geotextile", 0.0, geotextile_thickness_m, "#5e5ce6"),
        (
            "reactive keratin core",
            geotextile_thickness_m,
            geotextile_thickness_m + core_thickness_m,
            "#30d158",
        ),
        (
            "upper carrier geotextile",
            geotextile_thickness_m + core_thickness_m,
            2.0 * geotextile_thickness_m + core_thickness_m,
            "#5e5ce6",
        ),
    ]

    figure = go.Figure()
    for name, z0, z1, colour in layers:
        x = [0, tile_width_m, tile_width_m, 0, 0, tile_width_m, tile_width_m, 0]
        y = [0, 0, tile_length_m, tile_length_m, 0, 0, tile_length_m, tile_length_m]
        z = [z0] * 4 + [z1] * 4
        figure.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=[value * 1000.0 for value in z],
                i=[0, 0, 0, 0, 4, 4, 0, 1, 1, 2, 2, 3],
                j=[1, 2, 4, 3, 5, 6, 1, 5, 2, 6, 3, 7],
                k=[2, 3, 5, 7, 6, 7, 5, 4, 6, 5, 7, 4],
                color=colour,
                opacity=0.55,
                name=f"{name} ({(z1 - z0) * 1000:.0f} mm)",
                showlegend=True,
                hovertemplate=f"{name}<br>{(z1 - z0) * 1000:.1f} mm<extra></extra>",
            )
        )

    total_mm = (2.0 * geotextile_thickness_m + core_thickness_m) * 1000.0
    figure.update_layout(
        title={
            "text": (
                "Mat construction: reactive core encapsulated between two "
                f"carrier geotextiles<br><sub>Total {total_mm:.0f} mm. "
                "Vertical scale hugely exaggerated: this is a one metre square "
                "of a tile tens of metres across. The geotextiles are inert "
                "diffusive resistances and are credited with no capacity. This "
                "construction is established practice and no novelty is claimed "
                "for it.</sub>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        scene={
            "xaxis": {"title": "east (m)"},
            "yaxis": {"title": "north (m)"},
            "zaxis": {"title": "height through the mat (mm)"},
            "aspectratio": {"x": 1.0, "y": 1.0, "z": 0.6},
            "camera": {"eye": {"x": 1.6, "y": 1.5, "z": 1.0}},
        },
        template=_DARK,
        margin={"l": 10, "r": 10, "t": 120, "b": 10},
    )
    return figure


def layer_profile_3d(
    tiles: Sequence[Any],
    element: str,
    *,
    geotextile_thickness_m: float = 0.003,
    title: str | None = None,
):
    """Sorbed load through the mat thickness, tile by tile, as a 3-D surface.

    The x axis is the tile, the y axis is height through the reactive core, and
    the surface is the sorbed load. It shows what a plan view cannot: the
    sorption front sitting near the sediment face and working upward, and which
    tiles are further through it than others.
    """
    import plotly.graph_objects as go

    usable = [tile for tile in tiles if element in tile.sorbed_kg_per_kg]
    if not usable:
        raise ValueError(f"no tile carries a sorbed profile for {element!r}")

    profiles = [np.asarray(tile.sorbed_kg_per_kg[element], dtype=float) for tile in usable]
    n_nodes = min(profile.size for profile in profiles)
    matrix = np.stack([profile[:n_nodes] for profile in profiles], axis=0)

    core_mm = usable[0].geometry.thickness_m * 1000.0
    geo_mm = geotextile_thickness_m * 1000.0
    # z = 0 is the sediment face of the CORE, which sits above the lower
    # geotextile, so the core spans [geo_mm, geo_mm + core_mm].
    heights = geo_mm + np.linspace(0.0, core_mm, n_nodes)
    labels = [tile.tile_id for tile in usable]

    figure = go.Figure(
        data=[
            go.Surface(
                x=np.arange(len(usable)),
                y=heights,
                z=matrix.T * 1.0e6,  # kg/kg -> mg/kg
                colorscale="Viridis",
                colorbar={"title": f"{element} sorbed (mg/kg)"},
                hovertemplate=(
                    "tile %{x}<br>height %{y:.1f} mm"
                    f"<br>{element} %{{z:.3g}} mg/kg<extra></extra>"
                ),
            )
        ]
    )
    figure.update_layout(
        title={
            "text": (
                title
                or f"{element} sorbed load through the reactive core, per tile"
            )
            + (
                "<br><sub>Height is measured from the base of the mat, so the "
                f"core occupies {geo_mm:.0f} to {geo_mm + core_mm:.0f} mm; the "
                "carrier geotextiles hold no load by construction. "
                f"{SYNTHETIC_BANNER}.</sub>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        scene={
            "xaxis": {
                "title": "tile",
                "tickmode": "array",
                "tickvals": list(range(len(usable))),
                "ticktext": labels,
            },
            "yaxis": {"title": "height through the mat (mm)"},
            "zaxis": {"title": f"{element} sorbed (mg/kg)"},
            "camera": {"eye": {"x": 1.8, "y": -1.5, "z": 1.1}},
        },
        template=_DARK,
        margin={"l": 10, "r": 10, "t": 110, "b": 10},
    )
    return figure


def plume_surface_3d(grid, field, element: str, *, title: str | None = None):
    """The overlying plume as a 3-D surface over the seabed plan.

    The same field as the flat heatmap, given a height so the shape of the
    footprint downstream is readable. Height is concentration, not depth: this
    is not a picture of the water column.
    """
    import plotly.graph_objects as go

    values = np.asarray(field.concentration_kg_per_m3[element], dtype=float)
    values = values.reshape(grid.ny, grid.nx) * 1.0e9  # kg/m3 -> ng/L
    x = grid.origin_x_m + (np.arange(grid.nx) + 0.5) * grid.dx_m
    y = grid.origin_y_m + (np.arange(grid.ny) + 0.5) * grid.dy_m

    figure = go.Figure(
        data=[
            go.Surface(
                x=x,
                y=y,
                z=values,
                colorscale="Turbo",
                colorbar={"title": f"{element} (ng/L)"},
                hovertemplate=(
                    "east %{x:.0f} m<br>north %{y:.0f} m"
                    f"<br>{element} %{{z:.3g}} ng/L<extra></extra>"
                ),
            )
        ]
    )
    figure.update_layout(
        title={
            "text": (
                title or f"{element} in the overlying water, as a surface"
            )
            + (
                "<br><sub>Height is concentration, not depth. The model is "
                f"depth-averaged, so this is not a water column. "
                f"{SYNTHETIC_BANNER}.</sub>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        scene={
            "xaxis": {"title": "east (m)"},
            "yaxis": {"title": "north (m)"},
            "zaxis": {"title": f"{element} (ng/L)"},
            "camera": {"eye": {"x": 1.7, "y": -1.6, "z": 0.9}},
        },
        template=_DARK,
        margin={"l": 10, "r": 10, "t": 110, "b": 10},
    )
    return figure
