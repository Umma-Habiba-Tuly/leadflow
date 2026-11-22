"""Load and validate the labelled lead dataset, and convert your own labelled CSV into it."""
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from evals.metrics import LABELS

DEFAULT_PATH = Path(__file__).parent / "dataset.json"


@dataclass
class Case:
    id: str
    campaign: str
    niche: str
    location: str
    offer: str
    name: str
    website: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    has_email: bool
    label: str
    note: str = ""


def parse_dataset(data: dict) -> List[Case]:
    """Turn the JSON structure into Cases, raising ValueError with a clear message if it is
    malformed. A silent typo in a label would quietly corrupt every metric."""
    campaigns: Dict[str, dict] = data.get("campaigns") or {}
    cases: List[Case] = []
    seen = set()
    for raw in data.get("cases") or []:
        cid = raw.get("id")
        if not cid or cid in seen:
            raise ValueError(f"Missing or duplicate case id: {cid!r}")
        seen.add(cid)
        if raw.get("label") not in LABELS:
            raise ValueError(f"{cid}: label must be one of {LABELS}, got {raw.get('label')!r}")
        camp = campaigns.get(raw.get("campaign"))
        if not camp or not all(camp.get(k) for k in ("niche", "location", "offer")):
            raise ValueError(f"{cid}: unknown or incomplete campaign {raw.get('campaign')!r}")
        if not (raw.get("name") or "").strip():
            raise ValueError(f"{cid}: name is required")
        cases.append(
            Case(
                id=cid,
                campaign=raw["campaign"],
                niche=camp["niche"],
                location=camp["location"],
                offer=camp["offer"],
                name=raw["name"],
                website=raw.get("website"),
                address=raw.get("address"),
                rating=raw.get("rating"),
                review_count=raw.get("review_count"),
                has_email=bool(raw.get("has_email")),
                label=raw["label"],
                note=raw.get("note", ""),
            )
        )
    if not cases:
        raise ValueError("Dataset has no cases")
    return cases


def load_dataset(path: Path = DEFAULT_PATH) -> List[Case]:
    return parse_dataset(json.loads(Path(path).read_text(encoding="utf-8")))


def _num(value: str, cast):
    value = (value or "").strip()
    return cast(value) if value else None


def cases_from_csv(text: str) -> dict:
    """Convert YOUR labelled export into the dataset format.

    CSV columns: name, label (good/maybe/poor), niche, location, offer  (required)
                 website, address, rating, review_count, email, note     (optional)
    Rows sharing the same niche+location+offer become one campaign.
    """
    campaigns: Dict[str, dict] = {}
    cases = []
    for i, row in enumerate(csv.DictReader(text.splitlines()), start=1):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        key_tuple = (row.get("niche", ""), row.get("location", ""), row.get("offer", ""))
        key = next((k for k, v in campaigns.items() if (v["niche"], v["location"], v["offer"]) == key_tuple), None)
        if key is None:
            key = f"c{len(campaigns) + 1}"
            campaigns[key] = {"niche": key_tuple[0], "location": key_tuple[1], "offer": key_tuple[2]}
        cases.append(
            {
                "id": f"mine-{i:03d}",
                "campaign": key,
                "name": row.get("name", ""),
                "website": row.get("website") or None,
                "address": row.get("address") or None,
                "rating": _num(row.get("rating"), float),
                "review_count": _num(row.get("review_count"), int),
                "has_email": bool(row.get("email")),
                "label": row.get("label", "").lower(),
                "note": row.get("note", ""),
            }
        )
    data = {"campaigns": campaigns, "cases": cases}
    parse_dataset(data)  # validate now so mistakes surface at conversion time
    return data
