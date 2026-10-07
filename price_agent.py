#!/usr/bin/env python3
"""Audit comparable shelf prices in two channels from a CSV of store observations.

This is a rules-based, offline analyzer. Matching on product text produces candidate
matches, not verified identical products; a consistent barcode can verify a match.
The bundled input is synthetic and all its outputs are illustrative.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


CHANNELS = {"kirana", "modern"}
MISSING_PRICE = {"", "unclear", "unknown", "na", "n/a", "-"}
SIZE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*(ml|l|g|kg)$", re.IGNORECASE)
REQUIRED = {"store_id", "store_type", "brand", "variant", "pack_size", "promo"}


@dataclass(frozen=True)
class Observation:
    row: int
    store_id: str
    channel: str
    brand: str
    variant: str
    pack_size: str
    key: tuple[str, str, str]
    price: Decimal | None
    promo: bool | None
    barcode: str
    source: str


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def _pack_size(value: str, row: int) -> str:
    match = SIZE_PATTERN.fullmatch(_clean_text(value))
    if not match or Decimal(match.group(1)) <= 0:
        raise ValueError(f"CSV row {row}: pack_size must be a positive number followed by g, kg, ml or l")
    amount = Decimal(match.group(1)).normalize()
    return f"{format(amount, 'f')} {match.group(2).lower()}"


def _promo(value: str | None) -> bool | None:
    text = _clean_text(value).casefold()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def _source(value: str | None) -> str:
    return re.sub(r"[\s-]+", "_", _clean_text(value).casefold())


def _read(path: Path) -> tuple[list[Observation], list[dict], int]:
    observations: list[Observation] = []
    review: list[dict] = []
    invalid_prices = 0
    stores: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        missing = REQUIRED - set(reader.fieldnames)
        if not ({"price", "listed_price_inr"} & set(reader.fieldnames)):
            missing.add("price (or listed_price_inr)")
        if missing:
            raise ValueError("CSV is missing columns: " + ", ".join(sorted(missing)))
        for line, raw in enumerate(reader, start=2):
            if None in raw:
                raise ValueError(f"CSV row {line}: too many fields")
            if not any(_clean_text(v) for v in raw.values()):
                continue
            store = _clean_text(raw["store_id"])
            channel = _clean_text(raw["store_type"]).lower()
            brand = _clean_text(raw["brand"])
            variant = _clean_text(raw["variant"])
            if not store or not brand or not variant or channel not in CHANNELS:
                raise ValueError(f"CSV row {line}: store_id, store_type, brand and variant are required; store_type must be kirana or modern")
            if store in stores and stores[store] != channel:
                raise ValueError(f"CSV row {line}: store {store} appears in both channels")
            stores[store] = channel
            size = _pack_size(raw["pack_size"], line)
            key = (brand.casefold(), variant.casefold(), size.casefold())
            price_text = _clean_text(raw.get("price") or raw.get("listed_price_inr"))
            price: Decimal | None = None
            if price_text.casefold() not in MISSING_PRICE:
                try:
                    price = Decimal(price_text)
                    if not price.is_finite() or price <= 0:
                        raise InvalidOperation
                except InvalidOperation:
                    price = None
                    invalid_prices += 1
                    review.append({"severity": "high", "title": "Invalid listed price", "detail": f"CSV row {line}: '{price_text}' is not a positive INR amount. Excluded from comparisons.", "store_id": store, "row": line})
            else:
                review.append({"severity": "medium", "title": "Unclear listed price", "detail": f"CSV row {line}: price is missing or unclear. Check the shelf or pack before comparing.", "store_id": store, "row": line})
            promo = _promo(raw["promo"])
            if promo is None:
                review.append({"severity": "medium", "title": "Promo status unclear", "detail": f"CSV row {line}: promo must be true/false or yes/no. Excluded from regular-price comparisons.", "store_id": store, "row": line})
            observations.append(Observation(line, store, channel, brand, variant, size, key,
                                            price, promo, _clean_text(raw.get("barcode")),
                                            _source(raw.get("price_source"))))
    return observations, review, invalid_prices


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _percentage(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def analyze(path: Path) -> dict:
    """Return an explainable, deterministic report. Modern minus kirana is the sign convention."""
    rows, review, invalid_prices = _read(path)
    by_store_sku: dict[tuple[str, tuple[str, str, str]], list[Observation]] = defaultdict(list)
    by_sku: dict[tuple[str, str, str], list[Observation]] = defaultdict(list)
    for item in rows:
        by_store_sku[(item.store_id, item.key)].append(item)
        by_sku[item.key].append(item)

    clean_store_prices: dict[tuple[str, tuple[str, str, str]], Decimal] = {}
    clean_store_sources: dict[tuple[str, tuple[str, str, str]], list[str]] = {}
    conflicting = 0
    for (store, key), group in sorted(by_store_sku.items()):
        prices = {item.price for item in group if item.price is not None}
        if len(prices) > 1:
            conflicting += 1
            formatted = ", ".join(str(p) for p in sorted(prices))
            review.append({"severity": "high", "title": "Conflicting prices within a store",
                           "detail": f"{group[0].brand} {group[0].variant} {group[0].pack_size} has prices INR {formatted} in {store} (CSV rows {', '.join(str(x.row) for x in group)}). All observations for this store/product were excluded.",
                           "store_id": store, "rows": [x.row for x in group]})
            continue
        # Multiple photos of the same store must count once; promotions and unclear
        # promo flags are excluded even if another photo has a readable price.
        eligible = [x for x in group if x.price is not None and x.promo is False]
        if eligible:
            clean_store_prices[(store, key)] = eligible[0].price
            clean_store_sources[(store, key)] = [x.source for x in eligible]

    comparisons: list[dict] = []
    source_mismatches = 0
    for key, group in sorted(by_sku.items()):
        barcodes = {x.barcode.casefold() for x in group if x.barcode}
        if len(barcodes) > 1:
            review.append({"severity": "high", "title": "Barcode mismatch for candidate product",
                           "detail": f"{group[0].brand} {group[0].variant} {group[0].pack_size} has different barcodes. Confirm the exact product; excluded from comparisons."})
            continue
        by_channel: dict[str, list[dict]] = {"kirana": [], "modern": []}
        for store, channel in sorted({(x.store_id, x.channel) for x in group}):
            price = clean_store_prices.get((store, key))
            if price is not None:
                by_channel[channel].append({"store_id": store, "price_inr": _money(price)})
        if not all(by_channel.values()):
            continue
        used_sources = [source for channel in CHANNELS for x in by_channel[channel]
                        for source in clean_store_sources[(x["store_id"], key)]]
        known_sources = sorted({source for source in used_sources if source})
        if len(known_sources) > 1:
            source_mismatches += 1
            review.append({"severity": "high", "title": "Inconsistent price sources",
                           "detail": f"{group[0].brand} {group[0].variant} {group[0].pack_size} uses {', '.join(known_sources)} among eligible store prices. Compare the same price basis; excluded from comparisons."})
            continue
        source_status = ("unrecorded" if not known_sources else
                         "partially_unrecorded" if "" in used_sources else "consistent")
        kirana = _median([clean_store_prices[(x["store_id"], key)] for x in by_channel["kirana"]])
        modern = _median([clean_store_prices[(x["store_id"], key)] for x in by_channel["modern"]])
        verified = bool(barcodes) and all(x.barcode for x in group)
        comparisons.append({
            "brand": group[0].brand, "variant": group[0].variant, "pack_size": group[0].pack_size,
            "kirana_price": _money(kirana), "modern_price": _money(modern),
            "difference_inr": _money(modern - kirana),
            "difference_pct": _percentage((modern - kirana) / kirana * 100),
            "kirana_stores": len(by_channel["kirana"]), "modern_stores": len(by_channel["modern"]),
            "store_prices": by_channel, "verified": verified,
            "verification_status": "barcode_matched" if verified else "candidate_match_needs_barcode",
            "price_source_status": source_status,
        })

    review.sort(key=lambda item: (0 if item["severity"] == "high" else 1,
                                  item.get("store_id", ""), item.get("row", item.get("rows", [0])[0]), item["title"]))
    return {
        "meta": {"title": "ShelfScout · Price Check", "category": "sunscreen",
                 "synthetic": bool(rows) and all("fake test data" in (r.get("notes") or "").casefold()
                                                for r in _read_notes(path)),
                 "match_rule": "brand + variant + pack size, with unit; unverified without consistent barcode",
                 "price_rule": "Median of one clear, non-promo listed price per store and channel, only for candidate products in both channels. Conflicting store/product prices are excluded.",
                 "price_source_rule": "Differing known sources such as shelf_label and pack_mrp are excluded. Missing sources remain candidate comparisons and require field confirmation; the bundled sample has no recorded source.",
                 "difference_rule": "Modern minus kirana; percentage relative to kirana."},
        "summary": {"rows": len(rows), "stores": len({x.store_id for x in rows}),
                    "candidate_skus": len(by_sku),
                    "cross_channel_skus": sum(len({x.channel for x in group}) == 2 for group in by_sku.values()),
                    "comparable_skus": len(comparisons),
                    "unclear_prices": sum(x.price is None for x in rows) - invalid_prices,
                    "invalid_prices": invalid_prices, "conflicting_store_skus": conflicting,
                    "source_mismatch_skus": source_mismatches,
                    "missing_price_source_observations": sum(not x.source for x in rows),
                    "promo_observations": sum(x.promo is True for x in rows),
                    "unknown_promo_observations": sum(x.promo is None for x in rows),
                    "regular_store_prices": len(clean_store_prices)},
        "comparisons": comparisons,
        "review_queue": review,
    }


def _read_notes(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "sample_shelf_data.csv")
    parser.add_argument("--output", type=Path, default=root / "report.json")
    args = parser.parse_args()
    result = analyze(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {result['summary']['comparable_skus']} candidate comparisons from {result['summary']['rows']} rows")


if __name__ == "__main__":
    main()
