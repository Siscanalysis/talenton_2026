"""Measure exact within-step reuse against independent per-tile advancement.

python tools/benchmark_layer_memo.py --days 30

The reference path calls the same physical solver once per tile, bypassing only
the reuse optimisation. Full scientific histories and metadata are compared,
including exact array bytes. Performance is a local wall-clock observation.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
import numpy as np
from reactive_seabed_mat.config import RunConfig, config_to_dict
from reactive_seabed_mat.coastal_transport import seabed_source as ss
from reactive_seabed_mat.reactive_layer import advance_reactive_layer
from reactive_seabed_mat.scenarios import run


def identical(actual, expected):
    if isinstance(expected, np.ndarray):
        assert actual.shape == expected.shape and actual.dtype == expected.dtype
        assert actual.tobytes() == expected.tobytes()
    elif is_dataclass(expected):
        assert type(actual) is type(expected)
        for field in fields(expected):
            identical(getattr(actual,field.name),getattr(expected,field.name))
    elif isinstance(expected,Mapping):
        assert actual.keys() == expected.keys()
        for key in expected:
            identical(actual[key],expected[key])
    elif isinstance(expected,(tuple,list)):
        assert len(actual) == len(expected)
        for left,right in zip(actual,expected):
            identical(left,right)
    else:
        assert actual == expected


def naive_steps(config, field, tiles, hotspot, forcing, materials, dt):
    exchanges = ss.build_seabed_exchange(field,tiles,hotspot,forcing,max(dt,config.dt_s))
    by_id = {e.tile_id:replace(e,environment={**e.environment,
        'burial_resistance_s_per_m':config.degradation.burial_resistance_s_per_m,
        'fouling_bypass_coupling':config.degradation.fouling_bypass_coupling}) for e in exchanges}
    return [advance_reactive_layer(tile,by_id[tile.tile_id],materials,dt) for tile in tiles if tile.tile_id in by_id]


def main(days,output):
    config = replace(RunConfig(),duration_s=days*86400,plume=replace(RunConfig().plume,sample_years=()))
    cached_path = run._layer_steps
    started = time.perf_counter()
    cached = run.run_mat_timeline(config)
    cached_seconds = time.perf_counter()-started
    try:
        run._layer_steps = naive_steps
        started = time.perf_counter()
        naive = run.run_mat_timeline(config)
        naive_seconds = time.perf_counter()-started
    finally:
        run._layer_steps = cached_path
    identical(cached,naive)
    result = {'duration_days':days,'cached_seconds':cached_seconds,'naive_seconds':naive_seconds,
              'speedup':naive_seconds/cached_seconds,'complete_result_exactly_equal':True,
              'python':platform.python_version(),'platform':platform.platform(),
              'runner_sha256':hashlib.sha256(Path(run.__file__).read_bytes()).hexdigest(),
              'config_sha256':hashlib.sha256(json.dumps(config_to_dict(config),sort_keys=True).encode()).hexdigest(),
              'comparison':'All fields of MatTimelineResult, recursively; arrays require identical shape, dtype and bytes',
              'caveat':'One local paired wall-clock measurement, cached path first; concurrent load and warm-up can affect speedup'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=float,default=30)
    parser.add_argument('--out',type=Path,default=Path('results/numerical-audit/layer_memo_benchmark.json'))
    args = parser.parse_args()
    main(args.days,args.out)
