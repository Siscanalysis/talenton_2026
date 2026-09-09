"""Reproduce the reactive-column numerical audit and publication figures.

Run with this checkout's src on PYTHONPATH. The short nonlinear test deliberately
uses a small capacity to exercise breakthrough in days; it does not recalibrate
the scenario material. BDF independently integrates the face-flux equations.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from reactive_seabed_mat.config import RunConfig
from reactive_seabed_mat.reactive_layer import build_material_map, build_tile_geometry
from reactive_seabed_mat.reactive_layer.column import (
    ColumnParameters, bottom_conductance, build_column_parameters,
    discrete_steady_state_flux_kg_per_m2_per_s, solve_column_step,
    steady_state_flux_kg_per_m2_per_s, top_conductance,
)
from reactive_seabed_mat.reactive_layer.geotextile import (
    DEFAULT_GEOTEXTILE, encapsulated_conductances, geotextile_resistance_s_per_m,
)

DAY = 86400.0
BASELINE = ColumnParameters(0.010, 40, 0.5, 400.0, 2e-10, 3e-8, 5e-7, 5.0, 1e-3, 4e-4)


def faces(c, p, c_sed):
    flux = np.empty(p.n_nodes + 1)
    flux[0] = p.seepage_velocity_m_per_s * c_sed + bottom_conductance(p) * (c_sed - c[0])
    flux[1:-1] = (p.seepage_velocity_m_per_s * c[:-1]
                  - p.porosity * p.d_eff_m2_per_s * np.diff(c) / p.dz_m)
    flux[-1] = (p.seepage_velocity_m_per_s + top_conductance(p)) * c[-1]
    return flux


def main(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    p = replace(BASELINE, n_nodes=8, q_max_kg_per_kg=1e-5)
    n, duration = p.n_nodes, 14 * DAY
    marks = np.arange(1, 15) * DAY
    scales = np.r_[np.full(n, 1e-3), np.full(n, p.q_max_kg_per_kg)]

    def rate(t, state):
        c, q = state[:n], state[n:]
        dq = p.k_rate_per_s * (np.minimum(p.kd_m3_per_kg * c, p.q_max_kg_per_kg) - q)
        dq[q >= p.q_max_kg_per_kg] = 0.0
        dc = (-np.diff(faces(c, p, 1e-3)) / p.dz_m - p.bulk_density_kg_per_m3 * dq) / p.porosity
        return np.r_[dc, dq]

    reference = solve_ivp(rate, (0, duration), np.zeros(2*n), method="BDF",
                          dense_output=True, rtol=2e-9, atol=1e-14)
    if not reference.success:
        raise RuntimeError(reference.message)
    errors, trajectories = [], []
    max_residual = 0.0
    total_clipping = 0.0
    for hours in (6.0, 3.0, 1.5):
        dt = hours * 3600
        c, q = np.zeros(n), np.zeros(n)
        snapshots, ratios = [], [0.0]
        for index in range(round(duration / dt)):
            step = solve_column_step(c, q, p, dt, 1e-3, 0.0)
            c, q = step.porewater_kg_per_m3, step.sorbed_kg_per_kg
            max_residual = max(max_residual, abs(step.conservation_residual_kg_per_m2(dt)))
            total_clipping += step.clip_correction_kg_per_m2 + step.negative_clip_kg_per_m2
            ratios.append(step.flux_out_kg_per_m2_per_s / ((p.seepage_velocity_m_per_s+p.film_transfer_m_per_s)*1e-3))
            if (index + 1) % round(DAY / dt) == 0:
                snapshots.append(np.r_[c, q] / scales)
        error = float(np.max(np.abs(np.array(snapshots).T - reference.sol(marks) / scales[:, None])))
        errors.append(error)
        trajectories.append({"dt_hours": hours, "days": (np.arange(len(ratios))*dt/DAY).tolist(), "flux_ratio": ratios})

    nodes = (20, 40, 80, 160)
    continuum = steady_state_flux_kg_per_m2_per_s(BASELINE, 1e-3)
    spatial_flux = [discrete_steady_state_flux_kg_per_m2_per_s(replace(BASELINE, n_nodes=nz), 1e-3) for nz in nodes]
    spatial_errors = [abs(value / continuum - 1) for value in spatial_flux]

    # A prescribed source drop changes a normalized ratio instantly while the
    # stored concentration remains continuous. Resolve the later washout.
    inert = replace(BASELINE, n_nodes=8, q_max_kg_per_kg=0.0)
    dt = 1.5 * 3600
    c, q = np.zeros(8), np.zeros(8)
    for _ in range(round(14 * DAY / dt)):
        step = solve_column_step(c, q, inert, dt, 1e-3, 0)
        c, q = step.porewater_kg_per_m3, step.sorbed_kg_per_kg
    source_times, source_ratio, source_flux = [-dt/DAY, 0.0, 0.0], [], []
    for c_sed in (1e-3, 1e-3, 1e-4):
        step = solve_column_step(c, q, inert, 0, c_sed, 0)
        source_flux.append(step.flux_out_kg_per_m2_per_s)
        source_ratio.append(step.flux_out_kg_per_m2_per_s / ((inert.seepage_velocity_m_per_s+inert.film_transfer_m_per_s)*c_sed))
    for index in range(round(5 * DAY / dt)):
        step = solve_column_step(c, q, inert, dt, 1e-4, 0)
        c, q = step.porewater_kg_per_m3, step.sorbed_kg_per_kg
        source_times.append((index+1)*dt/DAY)
        source_flux.append(step.flux_out_kg_per_m2_per_s)
        source_ratio.append(step.flux_out_kg_per_m2_per_s / ((inert.seepage_velocity_m_per_s+inert.film_transfer_m_per_s)*1e-4))

    lock = replace(BASELINE, n_nodes=1)
    held = solve_column_step(np.zeros(1), np.array([lock.q_max_kg_per_kg]), lock, 21600, 0, 0)
    below = solve_column_step(np.zeros(1), np.array([lock.q_max_kg_per_kg*(1-1e-10)]), lock, 21600, 0, 0)

    config = RunConfig()
    geometry = build_tile_geometry(config.mat, config.hotspot, 0, 0)
    comparisons = {}
    driving = config.hotspot.schedule[0]
    for key, material in build_material_map(config.mat).items():
        col = build_column_parameters(geometry, material, n_nodes=config.mat.n_layer_nodes,
                                     seepage_velocity_m_per_s=driving.seepage_velocity_m_per_s,
                                     film_transfer_m_per_s=config.hotspot.film_transfer_m_per_s)
        gb, gt = encapsulated_conductances(clean_bottom_conductance_m_per_s=bottom_conductance(col),
                                           clean_top_conductance_m_per_s=top_conductance(col),
                                           bottom_layer=DEFAULT_GEOTEXTILE, top_layer=DEFAULT_GEOTEXTILE)
        cs = driving.porewater_kg_per_m3[key]
        v = col.seepage_velocity_m_per_s
        growth = np.exp(v * col.thickness_m / (col.porosity*col.d_eff_m2_per_s))
        legacy = growth * cs / (1/(v+gt) + (growth-1)/v + geotextile_resistance_s_per_m(DEFAULT_GEOTEXTILE))
        corrected = discrete_steady_state_flux_kg_per_m2_per_s(col, cs, top_conductance_m_per_s=gt, bottom_conductance_m_per_s=gb)
        comparisons[key] = {"legacy_approximate_flux": float(legacy), "corrected_discrete_flux": corrected,
                            "relative_change": corrected/legacy-1}

    data = {
        "purpose": "Numerical verification and classification of ratio/source discontinuities; not material calibration",
        "transient_test_parameters": asdict(p), "bdf_rtol": 2e-9, "bdf_atol": 1e-14,
        "temporal_dt_hours": [6.0, 3.0, 1.5], "normalized_max_profile_errors": errors,
        "temporal_trajectories": trajectories, "max_mass_residual_kg_per_m2": max_residual,
        "total_clipping_kg_per_m2": total_clipping, "spatial_nodes": list(nodes),
        "spatial_continuum_flux": continuum, "spatial_relative_errors": spatial_errors,
        "baseline_barrier_comparison": comparisons,
        "source_step": {"days": source_times, "residual_flux_ratio": source_ratio, "flux_kg_per_m2_per_s": source_flux,
                        "instantaneous_ratio_multiplier": source_ratio[2]/source_ratio[0]},
        "capacity_lock_flush": {"dt_hours": 6, "exactly_full_flux": held.flux_out_kg_per_m2_per_s,
                                 "just_below_full_flux": below.flux_out_kg_per_m2_per_s,
                                 "note": "Finite discontinuity imposed by capacity-lock law; retained as an unvalidated modelling assumption"},
    }
    (output / "reactive_numerical_audit.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    times = np.linspace(0, duration, 500)
    reference_ratio = (p.seepage_velocity_m_per_s+top_conductance(p))*reference.sol(times)[n-1] / ((p.seepage_velocity_m_per_s+p.film_transfer_m_per_s)*1e-3)
    axes[0, 0].plot(times/DAY, reference_ratio, color="black", lw=2, label="Adaptive BDF reference")
    for trajectory in trajectories:
        axes[0, 0].plot(trajectory["days"], trajectory["flux_ratio"], label=f'Implicit {trajectory["dt_hours"]:g} h', alpha=0.8)
    axes[0, 0].set(xlabel="Time (days)", ylabel="Residual / bare flux", title="A  Nonlinear breakthrough verification")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].loglog([6, 3, 1.5], errors, "o-", color="#007a87")
    axes[0, 1].set(xlabel="Time step (hours)", ylabel="Maximum normalized profile error", title="B  Temporal convergence to BDF")
    axes[1, 0].loglog(nodes, spatial_errors, "o-", color="#007a87")
    axes[1, 0].set(xlabel="Number of layer cells", ylabel="Relative steady-flux error", title="C  Spatial convergence to continuum")
    axes[1, 1].plot(source_times, 1-np.array(source_ratio), color="#a34f19")
    axes[1, 1].axvline(0, color="gray", linestyle="--", lw=1)
    axes[1, 1].set(xlabel="Time since source decrease (days)", ylabel="Attenuation = 1 − residual / bare", title="D  Ratio response to a tenfold source drop")
    for ax in axes.flat:
        ax.grid(alpha=0.2)
    for extension in ("pdf", "png"):
        fig.savefig(output / f"reactive_numerical_audit.{extension}", dpi=180)
    plt.close(fig)
    print(json.dumps({key: data[key] for key in ("normalized_max_profile_errors", "spatial_relative_errors", "max_mass_residual_kg_per_m2", "total_clipping_kg_per_m2", "baseline_barrier_comparison", "capacity_lock_flush")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/numerical-audit"))
    main(parser.parse_args().output)
