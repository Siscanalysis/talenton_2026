"""Package validated manuscript files without temporary build artefacts."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'manuscript'
ALLOWED={'.tex','.bib','.bbl','.pdf','.png','.json','.csv','.txt','.md','.py','.ps1'}


def manuscript_files():
    for path in sorted(REPORT.rglob('*')):
        relative=path.relative_to(REPORT)
        if not path.is_file() or path.suffix not in ALLOWED:
            continue
        if any(part.startswith('.') for part in relative.parts) or path.name.startswith('draft.'):
            continue
        if path.name in {'delivery_manifest.json','manuscript_sources.zip'}:
            continue
        yield path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/delivery/manuscript_sources.zip')
    args=parser.parse_args()
    assert (REPORT/'manuscript.pdf').is_file()
    validation=json.loads((REPORT/'verification/pdf_validation.json').read_text())
    assert validation['scenarios_regenerated']==6 and not validation['latex_errors']
    paths=list(manuscript_files())
    manifest={'files':[{'path':p.relative_to(REPORT).as_posix(),
        'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
        'source_revision':json.loads((REPORT/'provenance.json').read_text())['scientific_source_revision'],
        'pdf_validation':validation,
        'excluded':'Temporary LaTeX files, local simulation caches, internal agent-development files and supplied article PDFs.'}
    target=REPORT/'delivery_manifest.json'
    target.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in paths+[target]:
            archive.write(path,path.relative_to(REPORT).as_posix())
    print(f'Packaged {len(paths)} files: {args.output} ({args.output.stat().st_size:,} bytes)')


if __name__=='__main__': main()
