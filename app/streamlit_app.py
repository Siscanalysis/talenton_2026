"""Local presentation app for the selective reactive seabed mat.

    streamlit run app/streamlit_app.py

Offline: no account, no API token, no map tile server. Everything on screen is
computed from the same modules the tests exercise, and every chart states its
provenance.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from reactive_seabed_mat.config import config_hash  # noqa: E402
from reactive_seabed_mat.scenarios import registry  # noqa: E402
from reactive_seabed_mat.scenarios.run import (  # noqa: E402
    run_mat_timeline,
    run_plume_window,
)
from reactive_seabed_mat.visualization import maps  # noqa: E402

_SECONDS_PER_YEAR = 365.25 * 86400.0

st.set_page_config(
    page_title="Reactive seabed mat", page_icon="🟩", layout="wide"
)


# ---------------------------------------------------------------------------
# Cached computation.  The cache key is the configuration hash, so changing any
# control invalidates exactly what it should.
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _timeline(config_key: str, _config):
    return run_mat_timeline(_config)


@st.cache_data(show_spinner=False)
def _window(config_key: str, _config, _tiles, elapsed_s: float, label: str):
    return run_plume_window(_config, _tiles, elapsed_s, label=label)


def _build_config():
    st.sidebar.header("Scenario")
    names = registry.list_scenarios()
    labels = {name: f"{registry.scenario_letter(name)} - {name}" for name in names}
    name = st.sidebar.selectbox(
        "Scenario", names, format_func=lambda n: labels[n], index=0
    )
    config = registry.build_scenario(name)

    st.sidebar.header("Mat design")
    thickness_mm = st.sidebar.slider(
        "Reactive-layer thickness (mm)", 1.0, 40.0,
        float(config.mat.thickness_m * 1000.0), 1.0,
    )
    coverage = st.sidebar.slider(
        "Coverage of the hotspot", 0.1, 1.0,
        float(config.mat.coverage_fraction), 0.05,
    )
    bulk_density = st.sidebar.slider(
        "Medium bulk density (kg/m3)", 150.0, 800.0,
        float(config.mat.bulk_density_kg_per_m3), 25.0,
    )

    st.sidebar.header("Source")
    leak_multiplier = st.sidebar.slider(
        "Leak strength (x baseline)", 0.2, 5.0, 1.0, 0.1
    )
    seepage_multiplier = st.sidebar.slider(
        "Seepage velocity (x baseline)", 0.2, 5.0, 1.0, 0.1
    )

    st.sidebar.header("Maintenance policy")
    policy_kind = st.sidebar.radio(
        "Policy",
        list(registry.POLICIES),
        index=list(registry.POLICIES).index(config.policy.kind),
        format_func=lambda k: {"none": "no mat", "fixed": "fixed interval",
                               "evidence_informed": "evidence informed"}[k],
        help="Only PolicyConfig.kind changes, so the three are compared under "
             "identical assumptions.",
    )

    st.sidebar.header("Timeline")
    years = st.sidebar.slider(
        "Simulated years", 0.5, 8.0, float(config.duration_years), 0.5
    )
    view_year = st.sidebar.slider("Map at year", 0.0, years, 0.0, 0.5)

    mat = replace(
        config.mat,
        thickness_m=thickness_mm / 1000.0,
        coverage_fraction=coverage,
        bulk_density_kg_per_m3=bulk_density,
    )
    schedule = tuple(
        replace(
            entry,
            porewater_kg_per_m3={
                element: value * leak_multiplier
                for element, value in entry.porewater_kg_per_m3.items()
            },
            seepage_velocity_m_per_s=entry.seepage_velocity_m_per_s
            * seepage_multiplier,
        )
        for entry in config.hotspot.schedule
    )
    config = replace(
        config,
        mat=mat,
        hotspot=replace(config.hotspot, schedule=schedule),
        duration_s=years * _SECONDS_PER_YEAR,
        plume=replace(config.plume, sample_years=(view_year,)),
    )
    config = registry.policy_variant(config, policy_kind)
    return config, name, view_year


def main() -> None:
    st.title("Selective reactive seabed mat")
    st.caption(
        "A thin, modular, retrievable reactive cap over an authorised "
        "contaminated seabed area. It attenuates the contaminant flux from the "
        "sediment into the overlying water."
    )
    st.warning(
        f"**{maps.SYNTHETIC_BANNER}.** Reactive caps and activated-carbon "
        "amendments are established practice and no novelty is claimed for "
        "them. Keratin parameters are literature values derated for seawater, "
        "not measurements of our material. No supplier has been contacted.",
        icon="⚠️",
    )

    config, name, view_year = _build_config()
    key = config_hash(config)
    elements = list(config.elements)
    primary = st.sidebar.selectbox("Element shown on maps", elements, index=0)

    st.sidebar.caption(f"config hash `{key}`  ·  seed {config.seed}")
    st.info(registry.scenario_description(name), icon="🧭")

    with st.spinner("Solving the reactive layer over the mat timeline..."):
        mat = _timeline(key, config)
    timeline = mat.timeline
    ledger = mat.mat_ledger
    captured = mat.captured_tiles
    hotspot_released = mat.hotspot_released_kg

    last = timeline[-1]
    columns = st.columns(4)
    columns[0].metric(
        f"{primary} flux attenuation",
        f"{last.attenuation[primary] * 100:.1f} %",
        help="1 - J_out / J_bare at the end of the timeline.",
    )
    columns[1].metric(
        f"{primary} media saturation", f"{last.saturation[primary] * 100:.0f} %"
    )
    columns[2].metric("Effective coverage", f"{last.mean_coverage * 100:.0f} %")
    columns[3].metric(
        f"{primary} retained in mat", f"{last.retained_kg[primary]:.3g} kg"
    )

    tab_map, tab_time, tab_ledger, tab_care, tab_assumptions = st.tabs(
        [
            "Seabed and plume maps",
            "Through time",
            "Mass ledger",
            "Maintenance",
            "Assumptions",
        ]
    )

    with tab_map:
        st.subheader(f"Maps at year {view_year:.1f}")
        st.caption(
            "The mat state is held fixed while the short plume window runs: a "
            "cap changes over years, a plume equilibrates in hours."
        )
        with st.spinner("Running the coastal plume window..."):
            window = _window(
                key,
                config,
                tuple(captured[view_year]),
                view_year * _SECONDS_PER_YEAR,
                f"{view_year:.1f} yr",
            )
        grid = window.field_with_mat.grid
        shown_tiles = captured[view_year]

        left, right = st.columns(2)
        left.plotly_chart(
            maps.seabed_flux_map(
                grid, window.source_with_mat, primary, tiles=shown_tiles
            ),
            use_container_width=True,
        )
        right.plotly_chart(
            maps.mat_condition_map(
                grid, window.source_with_mat, primary, tiles=shown_tiles
            ),
            use_container_width=True,
        )

        peak = max(
            window.peak_concentration(primary, with_mat=False),
            window.peak_concentration(primary, with_mat=True),
        )
        zmax = peak * 1e9 if peak > 0 else None  # kg/m3 -> ng/L
        left, right = st.columns(2)
        left.plotly_chart(
            maps.water_concentration_map(
                grid, window.field_without_mat, primary, zmax=zmax
            ),
            use_container_width=True,
        )
        right.plotly_chart(
            maps.water_concentration_map(
                grid, window.field_with_mat, primary, tiles=shown_tiles, zmax=zmax
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            maps.risk_ratio_map(
                grid,
                window.field_with_mat,
                window.field_without_mat,
                primary,
                tiles=shown_tiles,
            ),
            use_container_width=True,
        )
        st.caption(
            "The last map is a model comparison under identical forcing. It is "
            "not a compliance assessment: no regulatory threshold is applied "
            "anywhere in this demonstrator."
        )

    with tab_time:
        st.plotly_chart(
            maps.attenuation_timeline(timeline, elements), use_container_width=True
        )
        st.plotly_chart(
            maps.saturation_timeline(timeline, elements), use_container_width=True
        )

    with tab_ledger:
        st.subheader("Reactive layer budget, whole timeline")
        st.caption(
            "What entered through the tiles' sediment face equals what is "
            "retained plus what left into the water."
        )
        st.dataframe(
            {
                "element": list(ledger),
                "entered the mat (kg)": [
                    ledger[e].released_from_sediment_kg for e in ledger
                ],
                "retained (kg)": [ledger[e].retained_in_mat_kg for e in ledger],
                "left to water (kg)": [ledger[e].boundary_out_kg for e in ledger],
                "relative imbalance": [
                    f"{ledger[e].relative_imbalance:.2e}" for e in ledger
                ],
            },
            use_container_width=True,
        )
        st.subheader("Gross mass leaving the whole hotspot")
        st.caption(
            "Including the area no tile covers. Reported separately, and never "
            "added to the layer budget."
        )
        st.dataframe(
            {
                "element": list(hotspot_released),
                "released (kg)": [hotspot_released[e] for e in hotspot_released],
            },
            use_container_width=True,
        )

    with tab_care:
        st.subheader(f"Policy: {config.policy.kind}")
        st.caption(registry.POLICIES[config.policy.kind])
        if config.policy.kind == "none":
            st.info(
                "No mat is deployed in this variant, so there is nothing to "
                "maintain. It is the reference the other two are measured "
                "against.",
                icon="🧭",
            )
        else:
            columns = st.columns(4)
            columns[0].metric("Observations generated", f"{mat.n_observations:,}")
            columns[1].metric("Recommendations", f"{len(mat.recommendations)}")
            columns[2].metric("Accepted services", f"{len(mat.service_events)}")
            columns[3].metric(
                "Assumed service cost", f"EUR {mat.assumed_service_cost_eur:,.0f}"
            )
            st.caption(
                "The controller sees a record only once its `available_at_utc` "
                "has passed, so a laboratory result still in transit cannot "
                "influence an earlier decision. Every recommendation carries "
                "`human_confirmation_required = True` and "
                "`execution_mode = 'simulation_only'`."
            )
            if mat.recommendations:
                st.dataframe(
                    {
                        "decision time": [
                            str(r.decision_time_utc)[:10] for r in mat.recommendations
                        ],
                        "action": [r.action.value for r in mat.recommendations],
                        "tiles": [
                            ", ".join(r.target_tile_ids) or "-"
                            for r in mat.recommendations
                        ],
                        "evidence records": [
                            len(r.evidence_record_ids) for r in mat.recommendations
                        ],
                        "reason": [r.reason for r in mat.recommendations],
                    },
                    use_container_width=True,
                )
            if mat.service_events:
                st.subheader("Accepted service events")
                st.dataframe(
                    {
                        "date": [str(e.time_utc)[:10] for e in mat.service_events],
                        "tiles": [", ".join(e.tile_ids) for e in mat.service_events],
                        "retrieved (kg)": [
                            sum(e.retrieved_kg.values()) for e in mat.service_events
                        ],
                        "assumed cost (EUR)": [
                            e.cost_eur for e in mat.service_events
                        ],
                    },
                    use_container_width=True,
                )
            else:
                st.warning(
                    "No service event was accepted over this timeline. Under "
                    "the evidence-informed policy that is a result, not a bug: "
                    "with chemistry on one tile and no seepage measurement, the "
                    "estimated saturation interval stays too wide to justify a "
                    "vessel. The value of evidence-informed maintenance is "
                    "bounded by the monitoring programme that feeds it.",
                    icon="⚠️",
                )

    with tab_assumptions:
        st.subheader("Reactive medium: keratin, literature-derated")
        st.dataframe(
            {
                "element": [m.element for m in config.mat.media],
                "q_max (mg/g)": [m.q_max_kg_per_kg * 1e3 for m in config.mat.media],
                "Kd (m3/kg)": [m.kd_m3_per_kg for m in config.mat.media],
                "allocation": [m.allocation_fraction for m in config.mat.media],
                "provenance": [m.provenance for m in config.mat.media],
            },
            use_container_width=True,
        )
        st.markdown(
            "Published Pb capacities for keratin biofibres are **4 to 33 mg/g**, "
            "measured in deionised water at pH 4. In seawater at pH 8.2, "
            "PbCO3(aq) alone is about 41 % of dissolved lead and free Pb2+ is a "
            "small minority, while Ca and Mg outnumber the trace metal by orders "
            "of magnitude, so the operating capacity is set well below those "
            "figures.\n\n"
            "**No verified Hg capacity for a keratin biosorbent was found.** The "
            "Hg figure is a stated fraction of the stoichiometric thiol ceiling "
            "implied by keratin's 4 to 8 wt% sulfur. It is the weakest number in "
            "the model.\n\n"
            "Full derivation, sources and the list of experiments that would be "
            "needed before any of this is a claim: `docs/MATERIAL_KERATIN.md`. "
            "Limitations, including the risk that a sulfur-rich organic layer "
            "over anoxic sediment promotes **methylmercury** production: "
            "`docs/LIMITATIONS.md`."
        )


if __name__ == "__main__":
    main()
