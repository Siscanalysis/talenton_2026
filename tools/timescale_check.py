"""Reproduce temporal refinement, horizon, tidal-window and cadence studies.

python tools/timescale_check.py --out docs/TIMESCALES.md --workers 2

Source/configuration hashes identify cached results. Curves are not smoothed.
Window duration and tidal phase are distinct from numerical step refinement.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import numpy as np
from reactive_seabed_mat.config import config_to_dict
from reactive_seabed_mat.scenarios import registry
from reactive_seabed_mat.scenarios.run import run_mat_timeline, run_plume_window

YEAR, HOUR, DAY = 365.25 * 86400.0, 3600.0, 86400.0


def source_hash():
    digest = hashlib.sha256()
    for path in sorted((REPO / "src").rglob("*.py")) + [Path(__file__)]:
        digest.update(str(path.relative_to(REPO)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_task(spec):
    kind, value, scenario, cache, digest = spec
    base = registry.build_scenario(scenario)
    key = hashlib.sha256(json.dumps([kind, value, config_to_dict(base), digest], sort_keys=True).encode()).hexdigest()
    target = Path(cache) / f"{kind}_{key}.json"
    if target.exists():
        return kind, json.loads(target.read_text(encoding="utf-8")), True
    started = time.perf_counter()
    if kind == "refinement":
        config = replace(base, dt_s=value*HOUR, duration_s=2*YEAR)
        result = run_mat_timeline(config)
        point = result.timeline[-1]
        data = {"dt_h": value, "n_steps": int(np.ceil(config.duration_s/config.dt_s)),
                "attenuation_Pb": point.attenuation["Pb"], "saturation_Pb": point.saturation["Pb"],
                "retained_Pb_kg": result.mat_ledger["Pb"].retained_in_mat_kg,
                "hotspot_into_water_Pb_kg": result.hotspot_into_water_kg["Pb"],
                "imbalance": abs(result.mat_ledger["Pb"].relative_imbalance),
                "trajectory": [{"years": row.elapsed_years, "attenuation_Pb": row.attenuation["Pb"]} for row in result.timeline]}
    elif kind == "horizon":
        config = replace(base, duration_s=max(value)*YEAR, plume=replace(base.plume, sample_years=tuple(value)))
        result = run_mat_timeline(config, sample_every_s=config.dt_s)
        data = []
        for years in value:
            points = [row for row in result.timeline if abs(row.elapsed_s-years*YEAR)<1e-6]
            if not points:
                raise RuntimeError(f"Missing exact horizon sample at {years} years")
            point = points[-1]
            row = {"years": years, "services": sum(event.time_utc<=point.time_utc for event in result.service_events)}
            for e in config.elements:
                row.update({f"atten_{e}":point.attenuation[e], f"barrier_{e}":point.barrier_attenuation[e], f"sat_{e}":point.saturation[e]})
            data.append(row)
    elif kind == "window":
        timeline = run_mat_timeline(replace(base, duration_s=YEAR))
        data = []
        for hours in sorted(set(value)):
            config = replace(base, plume=replace(base.plume, window_s=hours*HOUR))
            result = run_plume_window(config, timeline.final_tiles, YEAR, label=f"{hours:g} h")
            peak, bare = result.peak_concentration("Pb"), result.peak_concentration("Pb",with_mat=False)
            data.append({"hours":hours, "tidal_cycles":hours*HOUR/base.forcing.tidal_period_s,
                         "terminal_phase_rad":float((base.forcing.tidal_phase_rad+2*np.pi*(YEAR+hours*HOUR)/base.forcing.tidal_period_s)%(2*np.pi)),
                         "peak_with_mat_ng_per_l":peak*1e9, "peak_without_mat_ng_per_l":bare*1e9,
                         "ratio":peak/bare if bare>0 else None,
                         "source_ratio":result.ledger_with_mat["Pb"].released_from_sediment_kg/result.ledger_without_mat["Pb"].released_from_sediment_kg,
                         "imbalance":abs(result.ledger_with_mat["Pb"].relative_imbalance)})
            print(f"  window {hours:g} h: Pb peak ratio {data[-1]['ratio']:.6f}",flush=True)
    elif kind == "coastal_refinement":
        timeline = run_mat_timeline(replace(base,duration_s=YEAR))
        data = []
        width,height = base.domain.nx*base.domain.dx_m,base.domain.ny*base.domain.dy_m
        for dx,dt in value:
            domain = replace(base.domain,nx=round(width/dx),ny=round(height/dx),dx_m=dx,dy_m=dx)
            config = replace(base,domain=domain,plume=replace(base.plume,dt_s=dt,window_s=24*HOUR))
            result = run_plume_window(config,timeline.final_tiles,YEAR,label=f"dx={dx:g} m, dt={dt:g} s")
            peak,bare = result.peak_concentration('Pb'),result.peak_concentration('Pb',with_mat=False)
            ledger = result.ledger_with_mat['Pb']
            data.append({'dx_m':dx,'dt_s':dt,'nx':domain.nx,'ny':domain.ny,
                         'peak_with_mat_ng_per_l':peak*1e9,'peak_without_mat_ng_per_l':bare*1e9,
                         'ratio':peak/bare if bare>0 else None,'water_Pb_kg':ledger.in_water_kg,
                         'numerical_correction_kg':ledger.numerical_correction_kg,
                         'imbalance':abs(ledger.relative_imbalance)})
            print(f"  coastal dx={dx:g} m dt={dt:g} s: peak {peak*1e9:.6g} ng/L",flush=True)
    elif kind == "cadence":
        config = replace(base,duration_s=4*YEAR,policy=replace(base.policy,decision_period_s=value*DAY))
        result = run_mat_timeline(config)
        schedule = sorted((row.station_id,str(row.observed_at_utc),row.parameter.value,row.method_id) for row in result.observations)
        data = {"days":value,"decisions":len(result.recommendations),"services":len(result.service_events),
                "observations":result.n_observations,"atten_Pb":result.timeline[-1].attenuation["Pb"],
                "cost_eur":result.assumed_service_cost_eur,
                "observation_schedule_sha256":hashlib.sha256(json.dumps(schedule).encode()).hexdigest()}
    else:
        raise ValueError(kind)
    seconds = time.perf_counter()-started
    if isinstance(data,dict):
        data["seconds"] = seconds
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,indent=2),encoding="utf-8")
    print(f"  finished {kind} {value} in {seconds:.1f} s",flush=True)
    return kind,data,False


def table(headers,rows):
    return "\n".join(["| " + " | ".join(headers) + " |","|"+"|".join("---" for _ in headers)+"|"]
                     + ["| "+" | ".join(str(v) for v in row)+" |" for row in rows])


def render(data,target,output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    refinement,horizon,window,cadence = [data[k] for k in ("refinement","horizon","window","cadence")]
    spread = float(np.ptp([r["attenuation_Pb"] for r in refinement]))
    finest = min(refinement,key=lambda r:r["dt_h"])
    default = min(refinement,key=lambda r:abs(r["dt_h"]-6))
    error = abs(default["attenuation_Pb"]-finest["attenuation_Pb"])
    retained_range = float(np.ptp([r["retained_Pb_kg"] for r in refinement]))
    ratios,peaks = [r["ratio"] for r in window],[r["peak_with_mat_ng_per_l"] for r in window]
    phase_rows = [r for r in window if abs(r["tidal_cycles"]-round(r["tidal_cycles"]))<1e-9]
    services = sorted(set(r["services"] for r in cadence))
    calendars_equal = len(set(r["observation_schedule_sha256"] for r in cadence))==1
    elements = data["elements"]
    data["conclusions"] = {"attenuation_refinement_spread":spread,"default_vs_finest_attenuation_difference":error,
        "retained_Pb_refinement_range_kg":retained_range,"window_peak_ratio_range":[min(ratios),max(ratios)],
        "window_with_mat_peak_range_ng_per_l":[min(peaks),max(peaks)],"cadence_service_counts":services,
        "cadence_observation_schedules_identical":calendars_equal}
    coastal = data['coastal_refinement']
    time_rows = sorted([r for r in coastal if r['dx_m']==10],key=lambda r:r['dt_s'])
    grid_rows = sorted([r for r in coastal if r['dt_s']==150],key=lambda r:r['dx_m'])
    temporal_change = time_rows[-1]['peak_with_mat_ng_per_l']/time_rows[0]['peak_with_mat_ng_per_l']-1
    spatial_change = next(r for r in grid_rows if r['dx_m']==10)['peak_with_mat_ng_per_l']/grid_rows[0]['peak_with_mat_ng_per_l']-1
    data['conclusions'].update({'coastal_600s_vs_150s_relative_peak_difference':temporal_change,
                               'coastal_10m_vs_5m_relative_peak_difference':spatial_change})
    (output/"timescale_audit.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
    sections = [f"""# Time scales: revised numerical and decision audit

Generated by `tools/timescale_check.py` for `{data['scenario']}`. Source SHA-256:
`{data['source_sha256']}`. Source unchanged during execution:
`{data['source_unchanged_during_run']}`. Data and unsmoothed PDF/PNG figures:
`results/timescale-audit/timescale_audit.*`. Wall time: {data['seconds']:.1f} s
with {data['workers']} workers.

These results supersede the old tables: geometry, initial/final timestamps,
discrete barrier and whole-hotspot source weighting use the revised model.
Physical parameters remain synthetic assumptions.

## 1. Reactive-layer time refinement

Each run covers exactly two years. Attenuation is the area-mixed reduction of
the whole-hotspot source, including bypass.
""",
    table(['step (h)','nominal intervals','Pb attenuation','Pb saturation','active Pb (kg)','Pb into water (kg)','mass imbalance'],
          [[r['dt_h'],r['n_steps'],f"{r['attenuation_Pb']:.7f}",f"{r['saturation_Pb']:.6f}",f"{r['retained_Pb_kg']:.6g}",f"{r['hotspot_into_water_Pb_kg']:.6g}",f"{r['imbalance']:.2e}"] for r in refinement]),
    f"""The terminal attenuation spread is **{spread:.3e}**. Six hours differs from
the finest tested step by **{error:.3e}**; the active Pb inventory range is
**{retained_range:.6g} kg**. These quantify these particular terminal metrics,
not convergence of every breakthrough feature or coastal concentration peak.
Independent BDF and spatial checks are in `results/numerical-audit`. A closed
mass ledger alone is insufficient.

## 2. Simulation horizon

Exact requested ages are sampled from one continuous trajectory through the
longest horizon, preserving its initial conditions and campaign history.
""",
    table(['years']+[f'{e} attenuation' for e in elements]+[f'{e} barrier' for e in elements]+['services'],
          [[r['years']]+[f"{r[f'atten_{e}']:.6f}" for e in elements]+[f"{r[f'barrier_{e}']:.6f}" for e in elements]+[r['services']] for r in horizon]),
    """The barrier is the exact stationary discrete transport operator, with the
same geometry, fouling, burial and bypass. Its difference from transient
attenuation contains reactive and dissolved storage history; it is not measured
sorbent efficiency. Horizon dependence is neither time-step error nor an
experimentally established service life.

## 3. Plume duration and tidal phase

Each coastal run starts from clean water with the exact one-year mat state and
a fixed source. Changing duration changes both spin-up and tidal endpoint phase.
Integer-cycle windows compare matching phases separately.
""",
    table(['hours','tidal cycles','terminal phase (rad)','with-mat peak (ng/L)','bare peak (ng/L)','peak ratio','source ratio','mass imbalance'],
          [[f"{r['hours']:.2f}",f"{r['tidal_cycles']:.3f}",f"{r['terminal_phase_rad']:.4f}",f"{r['peak_with_mat_ng_per_l']:.5g}",f"{r['peak_without_mat_ng_per_l']:.5g}",f"{r['ratio']:.6f}",f"{r['source_ratio']:.6f}",f"{r['imbalance']:.2e}"] for r in window]),
    f"""Terminal with-mat Pb maxima span **{min(peaks):.5g}–{max(peaks):.5g} ng/L**;
the with/bare peak ratio spans **{min(ratios):.6f}–{max(ratios):.6f}**. Absolute
peaks and ratios need not have the same sensitivity: uniform coverage and
linear transport can produce proportional sources and nearly constant ratios
while absolute peaks change with tide.
""",
    table(['matching-phase cycles','with-mat peak (ng/L)','bare peak (ng/L)'],
          [[f"{r['tidal_cycles']:.0f}",f"{r['peak_with_mat_ng_per_l']:.6g}",f"{r['peak_without_mat_ng_per_l']:.6g}"] for r in phase_rows]),
    """Matching-phase rows test approach to a periodic response, separately from
phase changes. This finite set does not prove a settled periodic state. A tidal
field need not become time independent; endpoint bumps alone do not diagnose
solver instability. This duration study and water conservation do not replace
coastal grid/time-step refinement, which remains a separately reported limit.

## 4. Decision cadence
""",
    f"Four years per run, with nominal porewater interval {data['chemistry_interval_days']:g} days and laboratory latency {data['lab_latency_days']:g} days.",
    table(['decision period (days)','recommendations','services','observations','Pb attenuation','assumed cost (EUR)'],
          [[r['days'],r['decisions'],r['services'],r['observations'],f"{r['atten_Pb']:.6f}",f"{r['cost_eur']:.2f}"] for r in cadence]),
    f"""Service-count values: **{services}**. Observation-calendar hashes identical
across cadences: **{calendars_equal}**. Calendar equality compares station,
collection time, parameter and method, not measured values or evidence available
at an individual decision. Cadence changes when evidence is reviewed and must
not itself create samples. Any service dependence must be interpreted together
with the evidence and policy.

All results are conditional on the assumed hotspot and material laws. They do
not constitute field validation. No trajectories were smoothed.
"""]
    sections.extend(["""## 5. Coastal time-step and grid refinement

The physical domain, exact one-year tile state, 24-hour window, initial field,
forcing phase and source are held fixed. Time steps 600, 300 and 150 s use a
10-m grid; grids 20, 10 and 5 m use 150 s. The hotspot and land edges align
with all three grids, avoiding a change in covered area. Concentration peaks
and water inventories are reported separately from mass closure.
""",table(['grid (m)','step (s)','cells','with-mat peak (ng/L)','bare peak (ng/L)','ratio','Pb in water (kg)','signed correction (kg)'],
          [[r['dx_m'],r['dt_s'],r['nx']*r['ny'],f"{r['peak_with_mat_ng_per_l']:.6g}",f"{r['peak_without_mat_ng_per_l']:.6g}",f"{r['ratio']:.7f}",f"{r['water_Pb_kg']:.6g}",f"{r['numerical_correction_kg']:.2e}"] for r in coastal]),
    f"""Relative terminal with-mat Pb peak difference, 600 s versus 150 s at 10 m:
**{100*temporal_change:.3f}%**. Difference, 10 m versus 5 m at 150 s:
**{100*spatial_change:.3f}%**. These are measured discretisation sensitivities,
not error bounds relative to an exact PDE solution. A coarse/fine comparison
does not by itself establish an asymptotic convergence rate, especially when
temporal and spatial error coexist. The default gallery's absolute peaks should
retain this numerical qualification even if with/bare ratios are stable.
"""])
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text("\n\n".join(sections),encoding="utf-8")
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes = plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
    for r in refinement:
        axes[0,0].plot([p['years'] for p in r['trajectory']],[p['attenuation_Pb'] for p in r['trajectory']],label=f"{r['dt_h']:g} h")
    axes[0,0].set(title='A  Whole-hotspot time refinement',xlabel='Mat age (years)',ylabel='Pb source attenuation')
    for e in elements:
        axes[0,1].plot([r['years'] for r in horizon],[r[f'atten_{e}'] for r in horizon],'o-',label=e)
    axes[0,1].set(title='B  Longer service histories',xlabel='Mat age (years)',ylabel='Whole-hotspot attenuation')
    axes[1,0].plot([r['hours'] for r in window],[r['peak_with_mat_ng_per_l'] for r in window],'o-',label='With mat')
    axes[1,0].plot([r['hours'] for r in window],[r['peak_without_mat_ng_per_l'] for r in window],'s--',label='Bare hotspot')
    axes[1,0].set(title='C  Tidal terminal snapshots',xlabel='Coastal window (hours)',ylabel='Terminal Pb maximum (ng/L)')
    axes[1,1].plot([r['days'] for r in cadence],[r['decisions'] for r in cadence],'o-',label='Recommendations')
    axes[1,1].plot([r['days'] for r in cadence],[r['services'] for r in cadence],'s-',label='Services')
    axes[1,1].set(title='D  Decision cadence',xlabel='Review period (days)',ylabel='Count in four years')
    for ax in axes.flat:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for extension in ('pdf','png'):
        fig.savefig(output/f'timescale_audit.{extension}',dpi=180)
    plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for ax,rows,variable,title in ((axes[0],time_rows,'dt_s','A  Coastal time refinement (10 m grid)'),
                                  (axes[1],grid_rows,'dx_m','B  Coastal grid refinement (150 s step)')):
        ax.plot([r[variable] for r in rows],[r['peak_with_mat_ng_per_l'] for r in rows],'o-',label='With mat')
        ax.plot([r[variable] for r in rows],[r['peak_without_mat_ng_per_l'] for r in rows],'s--',label='Bare hotspot')
        ax.set(title=title,xlabel='Time step (s)' if variable=='dt_s' else 'Grid spacing (m)',ylabel='Terminal Pb maximum (ng/L)')
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for extension in ('pdf','png'):
        fig.savefig(output/f'coastal_discretisation_audit.{extension}',dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('docs/TIMESCALES.md'))
    parser.add_argument('--data-dir',type=Path,default=Path('results/timescale-audit'))
    parser.add_argument('--scenario',default='progressive_saturation')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--quick',action='store_true')
    args = parser.parse_args()
    if args.workers<1:
        parser.error('--workers must be positive')
    args.data_dir.mkdir(parents=True,exist_ok=True)
    base,digest = registry.build_scenario(args.scenario),source_hash()
    steps = [12.,6.,3.] if args.quick else [24.,12.,6.,3.,1.]
    horizons = [1.,4.] if args.quick else [1.,2.,4.,8.,16.]
    windows = [6.,24.] if args.quick else [3.,6.,12.,24.,48.]
    if not args.quick:
        windows += [cycles*base.forcing.tidal_period_s/HOUR for cycles in (2,3,4)]
    cadences = [30.,180.] if args.quick else [15.,30.,90.,180.,365.]
    tasks = [('horizon',horizons),('refinement',min(steps)),('window',windows)]
    tasks += [('coastal_refinement',[(10.,600.),(10.,300.),(10.,150.),(20.,150.),(5.,150.)])]
    tasks += [('refinement',step) for step in steps if step!=min(steps)]
    tasks += [('cadence',days) for days in cadences]
    specs = [(kind,value,args.scenario,str(args.data_dir/'cache'),digest) for kind,value in tasks]
    data = {'scenario':args.scenario,'source_sha256':digest,'workers':args.workers,'elements':list(base.elements),
            'chemistry_interval_days':base.observations.porewater_sample_period_s/DAY,
            'lab_latency_days':base.observations.lab_latency_s/DAY,'refinement':[],'cadence':[]}
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_task,spec) for spec in specs]):
            kind,rows,cached = future.result()
            if kind in ('refinement','cadence'):
                data[kind].append(rows)
            else:
                data[kind] = rows
            print(f"Collected {kind}"+(' (cached)' if cached else ''),flush=True)
    data['refinement'].sort(key=lambda r:-r['dt_h'])
    data['cadence'].sort(key=lambda r:r['days'])
    data['seconds'] = time.perf_counter()-started
    data['source_unchanged_during_run'] = source_hash()==digest
    render(data,args.out,args.data_dir)
    print(f"Wrote {args.out} and {args.data_dir} in {data['seconds']:.1f} s",flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
