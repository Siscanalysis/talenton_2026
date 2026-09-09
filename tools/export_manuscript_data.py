"""Export audited local gallery runs to portable manuscript data.

The gzip pickles are a local build cache created by build_gallery.py, not an
interchange format. Never point this script at untrusted pickle files.
"""
from pathlib import Path
from dataclasses import asdict
from collections import Counter
import gzip
import json
import pickle
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from reactive_seabed_mat.config import config_to_dict
from reactive_seabed_mat.results import ledger_to_dict, write_json
from reactive_seabed_mat.cli import _write_result


def main():
    manifest = json.loads((ROOT / 'docs/gallery/cache_manifest.json').read_text())
    summaries, policies, audits = {}, {}, []
    output = ROOT / 'manuscript'
    for entry in manifest['runs']:
        with gzip.open(ROOT / '.revision_cache/gallery' / entry['cache_file'], 'rb') as handle:
            result = pickle.load(handle)
        config, maintenance = result.config, result.maintenance
        windows = []
        for window in result.windows:
            metrics = {}
            for e in config.elements:
                lm, lb = window.ledger_with_mat[e], window.ledger_without_mat[e]
                metrics[e] = {
                    'source_with_kg': lm.released_from_sediment_kg,
                    'source_bare_kg': lb.released_from_sediment_kg,
                    'area_attenuation': 1 - lm.released_from_sediment_kg / lb.released_from_sediment_kg,
                    'peak_with_ng_l': window.peak_concentration(e) * 1e9,
                    'peak_bare_ng_l': window.peak_concentration(e, with_mat=False) * 1e9,
                    'peak_ratio': window.peak_concentration(e) / window.peak_concentration(e, with_mat=False),
                    'ledger_with': ledger_to_dict(lm), 'ledger_bare': ledger_to_dict(lb),
                }
            windows.append({'years': window.elapsed_years, 'window_s': window.window_s, 'elements': metrics})
        recs = maintenance.observations
        summary = {'scenario': config.scenario, 'policy': config.policy.kind,
            'config_hash': entry['config_hash'], 'config': config_to_dict(config),
            'final': result.timeline[-1].to_dict(),
            'timeline': [p.to_dict() for p in result.timeline],
            'layer_ledger': {e: ledger_to_dict(l) for e,l in result.mat_ledger.items()},
            'hotspot_into_water_kg': dict(result.hotspot_into_water_kg),
            'hotspot_bare_reference_kg': dict(result.hotspot_released_kg),
            'windows': windows, 'services': [asdict(e) for e in maintenance.service_events],
            'service_cost_eur': maintenance.assumed_service_cost_eur,
            'observation_count': len(recs),
            'observation_kinds': dict(Counter(str(r.acquisition_kind.value) for r in recs)),
            'observation_parameters': dict(Counter(str(r.parameter) for r in recs)),
            'recommendations': dict(Counter(r.action.value for r in maintenance.recommendations)),
            'degradation_events': list(maintenance.degradation_events)}
        final = result.timeline[-1]
        final_window = result.windows[-1]
        grid = final_window.field_with_mat.grid
        area = config.hotspot.width_m * config.hotspot.length_m
        errors = {e: abs(np.sum(final_window.source_with_mat.flux_kg_per_m2_per_s[e])
                         * grid.dx_m * grid.dy_m - final.mean_residual_flux[e] * area)
                  / max(final.mean_residual_flux[e] * area, 1e-30) for e in config.elements}
        budget_errors = [abs(l.relative_imbalance) for l in result.mat_ledger.values()]
        budget_errors += [abs(l.relative_imbalance) for w in result.windows
                          for budget in (w.ledger_with_mat, w.ledger_without_mat) for l in budget.values()]
        audit = {'scenario': config.scenario, 'policy': config.policy.kind,
            'maximum_ledger_relative_imbalance': max(budget_errors),
            'final_timeline_source_relative_error': errors,
            'zero_time_inventory_kg': dict(result.timeline[0].retained_kg),
            'final_elapsed_s': final.elapsed_s, 'configured_duration_s': config.duration_s,
            'all_window_ages_valid': all(0 <= w.elapsed_years <= config.duration_years for w in result.windows),
            'unique_observation_ids': len({r.record_id for r in recs}) == len(recs)}
        assert max(budget_errors) < 1e-6, audit
        assert max(errors.values()) < 1e-10, audit
        assert audit['all_window_ages_valid'] and audit['unique_observation_ids'], audit
        assert final.elapsed_s == config.duration_s, audit
        audits.append(audit)
        if config.scenario == 'progressive_saturation':
            policies[config.policy.kind] = summary
        if config.policy.kind == 'evidence_informed' and '__' not in config.run_id:
            summaries[config.scenario] = summary
        _write_result(result, ROOT / 'results/revision')
    write_json(output / 'data/scenario_summary.json', list(summaries.values()))
    write_json(output / 'data/policy_summary.json', list(policies.values()))
    write_json(output / 'data/current_scenario_configurations.json',
               {name: summary['config'] for name, summary in summaries.items()})
    write_json(output / 'verification/scenario_audit.json', audits)
    print(f'Exported {len(summaries)} scenarios and {len(policies)} policies; all integration audits passed.')


if __name__ == '__main__':
    main()
