"""Standalone summary of the research evidence files.

Runnable example for the ``research/sensors`` branch.  It needs no map, no
network, no hardware and no part of ``src/``: it reads only the two JSON files
this branch owns and prints what they contain.

    python research/summarise_research.py

It also acts as a lint for the evidence files:

* every supplier record must carry exactly the eleven contract keys;
* ``status`` must come from the frozen five-word vocabulary;
* ``eu_member`` must be a boolean and must agree with the country;
* every record must carry a URL and an ISO access date.

A failure prints to stderr and sets a non-zero exit code, so this file can be
run in a pipeline without being a pytest test.  This branch writes no tests and
no application code (see ``docs/handoffs/research_sensors.md``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "references" / "evidence.json"
PRIOR_ART = HERE / "references" / "prior_art.json"

#: The exact record shape requested for ``evidence.json``.
REQUIRED_KEYS = (
    "supplier",
    "country",
    "eu_member",
    "model",
    "measures",
    "claim",
    "url",
    "access_date",
    "retrieval_status",
    "status",
    "notes",
)

#: Exactly one of these per supplier record.  Frozen vocabulary.
STATUS_VOCABULARY = frozenset(
    {
        "CURRENT_LISTING",
        "HISTORICAL_EVIDENCE",
        "INDEXED_LEAD_ONLY",
        "RESEARCH_PROTOTYPE",
        "NOT_SUITABLE",
    }
)

#: Countries appearing in the matrix, with their EU membership as of the
#: research snapshot date (2026-09-08).  Iceland, Norway and Switzerland are
#: European but not EU members; the United Kingdom left the EU in 2020.
EU_MEMBERSHIP = {
    "France": True,
    "Italy": True,
    "Denmark": True,
    "Netherlands": True,
    "Norway": False,
    "United Kingdom": False,
    "Switzerland": False,
    "Iceland": False,
}


def _load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing evidence file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path.name} must contain one JSON array")
    return payload


def check_evidence(records: list[dict]) -> list[str]:
    """Return a list of problems.  An empty list means the file is well formed."""
    problems: list[str] = []
    for index, record in enumerate(records):
        label = record.get("model", f"record {index}")
        keys = set(record)
        missing = set(REQUIRED_KEYS) - keys
        extra = keys - set(REQUIRED_KEYS)
        if missing:
            problems.append(f"{label}: missing keys {sorted(missing)}")
        if extra:
            problems.append(f"{label}: unexpected keys {sorted(extra)}")
        status = record.get("status")
        if status not in STATUS_VOCABULARY:
            problems.append(f"{label}: status {status!r} is outside the vocabulary")
        eu = record.get("eu_member")
        if not isinstance(eu, bool):
            problems.append(f"{label}: eu_member must be a boolean, got {eu!r}")
        else:
            country = record.get("country")
            expected = EU_MEMBERSHIP.get(country)
            if expected is None:
                problems.append(f"{label}: country {country!r} not in the EU table")
            elif expected is not eu:
                problems.append(
                    f"{label}: eu_member {eu} disagrees with country {country!r}"
                )
        url = record.get("url", "")
        if not isinstance(url, str) or not url.startswith("http"):
            problems.append(f"{label}: url is not an http(s) URL")
        access = record.get("access_date", "")
        if not isinstance(access, str) or len(access) != 10 or access[4] != "-":
            problems.append(f"{label}: access_date {access!r} is not ISO yyyy-mm-dd")
    return problems


def _bar(count: int) -> str:
    return "#" * count


def main() -> int:
    evidence = _load(EVIDENCE)
    prior_art = _load(PRIOR_ART)

    print("Selective reactive seabed mat: research evidence summary")
    print("Branch research/sensors. Research snapshot 2026-09-08.")
    print("No supplier has been contacted. Nothing here is a quotation.")
    print()

    problems = check_evidence(evidence)
    print(f"Supplier and service records : {len(evidence)}")
    print(f"Prior-art source records     : {len(prior_art)}")
    print(f"Schema problems              : {len(problems)}")
    print()

    by_status: dict[str, int] = {}
    for record in evidence:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
    print("Commercial status")
    for status in sorted(by_status, key=lambda key: (-by_status[key], key)):
        print(f"  {status:<20} {by_status[status]:>2}  {_bar(by_status[status])}")
    print()

    eu = sum(1 for record in evidence if record["eu_member"])
    print(f"EU member states     : {eu}")
    print(f"European non-EU      : {len(evidence) - eu}")
    print()

    print("Retrieval outcome")
    by_retrieval: dict[str, int] = {}
    for record in evidence:
        key = record["retrieval_status"]
        by_retrieval[key] = by_retrieval.get(key, 0) + 1
    for key in sorted(by_retrieval, key=lambda k: (-by_retrieval[k], k)):
        print(f"  {key:<20} {by_retrieval[key]:>2}  {_bar(by_retrieval[key])}")
    print()

    print("Records whose 'measures' field mentions a metal at all")
    print("(a mention is not a verified capability: read the notes)")
    metal_words = ("pb", "hg", "lead", "mercury", "metal")
    for record in evidence:
        measures = record["measures"].lower()
        if any(word in measures for word in metal_words):
            print(f"  [{record['status']:<19}] {record['supplier']}: {record['model']}")
    print()

    print("Headline finding")
    print("  No purchasable, currently confirmed continuous in-situ Pb or Hg sensor")
    print("  for seawater could be verified. The recommendation is continuous")
    print("  physical sensors plus passive and periodic chemical sampling.")
    print("  See research/sensors/measurement_chain.md.")
    print()

    if problems:
        print("PROBLEMS", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("Evidence files are well formed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
