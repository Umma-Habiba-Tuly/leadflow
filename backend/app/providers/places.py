"""Google Places API (New) text search: the official, ToS-compliant lead source."""
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.core.config import settings

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "nextPageToken",
    ]
)


@dataclass
class RawLead:
    source_id: str
    name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None


class PlacesNotConfigured(RuntimeError):
    pass


def search_places(niche: str, location: str, max_results: int = 20) -> List[RawLead]:
    if not settings.google_places_api_key:
        raise PlacesNotConfigured("GOOGLE_PLACES_API_KEY is not set")

    headers = {
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    results: List[RawLead] = []
    page_token: Optional[str] = None

    with httpx.Client(timeout=20) as client:
        while len(results) < max_results:
            body = {"textQuery": f"{niche} in {location}", "pageSize": min(20, max_results - len(results))}
            if page_token:
                body["pageToken"] = page_token
            resp = client.post(PLACES_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

            for p in data.get("places", []):
                results.append(
                    RawLead(
                        source_id=p["id"],
                        name=(p.get("displayName") or {}).get("text", "Unknown"),
                        website=p.get("websiteUri"),
                        phone=p.get("nationalPhoneNumber"),
                        address=p.get("formattedAddress"),
                        rating=p.get("rating"),
                        review_count=p.get("userRatingCount"),
                    )
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return results[:max_results]
