"""Validate and inventory the finished scientific manuscript.

Run after simulation export, figure/table generation and the complete LaTeX
build. This does not modify simulation inputs or publish anything remotely.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def latex_tool(name):
    found=shutil.which(name)
    if found: return found
    fallback=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/MiKTeX/miktex/bin/x64'/f'{name}.exe'
    if fallback.exists(): return str(fallback)
    raise FileNotFoundError(name)
def output(command):
    return subprocess.check_output(command,cwd=OUT,encoding='utf-8',errors='replace')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-revision',required=True)
    parser.add_argument('--test-log',type=Path,default=ROOT/'.revision_release_tests.log')
    args=parser.parse_args()
    raw_tests=args.test_log.read_bytes()
    test_text=raw_tests.decode('utf-16' if raw_tests.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    count=re.search(r'(\d+) passed',test_text)
    assert count and not re.search(r'\d+ (failed|error)',test_text), 'Full test suite did not pass.'
    (OUT/'verification/test_results.txt').write_text(test_text,encoding='utf-8')
    logs=(OUT/'manuscript.log').read_text(encoding='utf-8',errors='replace')
    bad=[line for line in logs.splitlines() if re.search(
        r'Overfull|Citation .+undefined|Reference .+undefined|undefined citations|^!|Fatal error',line)]
    assert not bad, '\n'.join(bad)
    pdf=OUT/'manuscript.pdf'
    text=output([latex_tool('pdftotext'),str(pdf),'-'])
    assert 'pending-source-commit' not in text and '??' not in text, 'Placeholder or unresolved reference in PDF.'
    info=output([latex_tool('pdfinfo'),str(pdf)])
    pages=int(re.search(r'Pages:\s+(\d+)',info).group(1))
    fonts=output([latex_tool('pdffonts'),str(pdf)])
    assert all(line.split()[-5]=='yes' for line in fonts.splitlines()[2:] if line.strip()), 'Unembedded PDF font.'
    (OUT/'verification/pdf_fonts.txt').write_text(fonts,encoding='utf-8')
    (OUT/'verification/pdf_info.txt').write_text(info,encoding='utf-8')
    bib=(OUT/'references.bib').read_text(encoding='utf-8')
    bibliography_entries=re.findall(r'@\w+\{([^,\s]+)',bib)
    assert len(bibliography_entries)==len(set(bibliography_entries))
    scenarios=json.loads((OUT/'data/scenario_summary.json').read_text())
    policies=json.loads((OUT/'data/policy_summary.json').read_text())
    audits=json.loads((OUT/'verification/scenario_audit.json').read_text())
    assert len(scenarios)==6 and len(policies)==3
    assert all(a['all_window_ages_valid'] and a['unique_observation_ids'] for a in audits)
    figures=json.loads((OUT/'data/gallery_plots.json').read_text())
    auxiliary=(OUT/'manuscript.aux').read_text(encoding='utf-8')
    bbl=(OUT/'manuscript.bbl').read_text(encoding='utf-8')
    validation={'pdf_pages':pages,'bibliography_entries':len(re.findall(r'\\bibitem',bbl)),
        'bibliography_database_entries':len(bibliography_entries),
        'vector_graphics':len(list((OUT/'figures').glob('*.pdf'))),
        'numbered_figures':len(re.findall(r'\\newlabel\{fig:',auxiliary)),
        'numbered_tables':len(re.findall(r'\\newlabel\{tab:',auxiliary)),
        'interactive_gallery_figures':len(figures),'tests_passed':int(count.group(1)),
        'scenarios_regenerated':6,'policies_regenerated':3,
        'latex_errors':False,'latex_overfull_boxes':False,
        'latex_undefined_citations':False,'latex_undefined_references':False,
        'placeholder_tokens_in_pdf':False,
        'maximum_scenario_ledger_relative_imbalance':max(a['maximum_ledger_relative_imbalance'] for a in audits),
        'scope':'All scenarios/policies and full numerical studies regenerated; all individual ledgers checked. These are numerical checks, not field validation.'}
    write(OUT/'verification/pdf_validation.json',validation)
    scientific_docs=['ASSUMPTIONS.md','MODEL_SPEC.md','DATA_CONTRACT.md','MATERIAL_KERATIN.md',
        'EVIDENCE_BASE.md','PRIOR_ART.md','LIMITATIONS.md','DEPLOYMENT_SCALE.md','TIMESCALES.md',
        'NUMERICAL_VERIFICATION.md','PAPER_PARAMETER_TRACEABILITY.md','SCIENTIFIC_REVISION.md']
    files=[]
    for folder in ['src','app','tests']:
        files.extend((ROOT/folder).rglob('*.py'))
    files.extend(ROOT/'docs'/name for name in scientific_docs)
    files.extend((ROOT/'research').rglob('*.json'))
    files.extend(ROOT/name for name in ['pyproject.toml','requirements.lock.txt','README.md'])
    files.extend(ROOT/'tools'/name for name in ['build_gallery.py','timescale_check.py','revision_numerics.py',
        'benchmark_layer_memo.py','export_manuscript_data.py','render_manuscript_tables.py','render_numerical_results.py'])
    files.extend([ROOT/'docs/gallery/index.html',ROOT/'docs/gallery/cache_manifest.json'])
    files=sorted(set(p for p in files if p.is_file()))
    gallery=json.loads((ROOT/'docs/gallery/cache_manifest.json').read_text())
    packages={name:importlib.metadata.version(name) for name in ['numpy','scipy','fipy','matplotlib','plotly','pytest']}
    provenance={'schema_version':'2.0','generated_utc':datetime.now(timezone.utc).isoformat(),
        'repository':'https://github.com/Siscanalysis/talenton_2026',
        'scientific_source_revision':args.source_revision,
        'baseline_revision':'158d103ec9deafe86d9ea142c0e292df456a3c59',
        'gallery_scientific_fingerprint':gallery['scientific_source_fingerprint'],
        'python_version':sys.version.split()[0],'packages':packages,
        'evidence_scope':'Executable science, tests, scientific documentation, literature registry and regenerated outputs. Internal development prompts/instructions/handoffs excluded.',
        'source_files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in files],
        'configurations':[{'scenario':s['scenario'],'policy':s['policy'],'config_hash':s['config_hash']} for s in scenarios+policies],
        'verification':validation}
    write(OUT/'provenance.json',provenance)
    print(json.dumps(validation,indent=2))


if __name__=='__main__': main()
