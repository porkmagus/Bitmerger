#!/usr/bin/env python3
"""Stress test the Bitmerger engine with the 5000-item vault."""

import json
import time
import sys
import os
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bitmerger import core
from bitmerger.undo_manager import UndoManager

VAULT_PATH = Path("/Users/sean/repos/bitmerger/tests/fixtures/large_vault.json")


def load_vault():
    with open(VAULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_load():
    print("\n[1] Load Vault")
    t0 = time.perf_counter()
    vault = load_vault()
    t1 = time.perf_counter()
    print(f"  JSON parse: {t1-t0:.3f}s")
    print(f"  Items: {len(vault['items'])}")
    print(f"  Folders: {len(vault['folders'])}")
    return vault


def test_engine_parse(vault):
    print("\n[2] Engine Parse")
    t0 = time.perf_counter()
    items, raw_data = core.load_vault(VAULT_PATH)
    t1 = time.perf_counter()
    print(f"  Parse time: {t1-t0:.3f}s")
    print(f"  Items parsed: {len(items)}")
    type_counts = {}
    for it in items:
        type_counts[it.type] = type_counts.get(it.type, 0) + 1
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")
    return raw_data, items


def test_dedup_analysis(items):
    print("\n[3] Dedup Analysis")
    t0 = time.perf_counter()
    clusters, comparisons = core.find_duplicates_by_type(items, threshold=0.85, fast=False)
    t1 = time.perf_counter()
    print(f"  Analysis time: {t1-t0:.3f}s")
    print(f"  Comparisons made: {comparisons}")
    print(f"  Clusters found: {len(clusters)}")
    if clusters:
        sizes = [len(c) for c in clusters]
        print(f"  Largest cluster: {max(sizes)} items")
        print(f"  Avg cluster size: {sum(sizes)/len(sizes):.1f}")
        confidences = [core.cluster_confidence(c) for c in clusters]
        print(f"  Avg confidence: {sum(confidences)/len(confidences)*100:.1f}%")
        print(f"  High confidence (>=90%): {sum(1 for x in confidences if x >= 0.90)}")
    return clusters


def test_merge_simulation(items, raw_data, clusters):
    print("\n[4] Merge Simulation")
    # Build cluster infos
    cluster_infos = []
    for i, cluster in enumerate(clusters):
        primary_idx = core.pick_primary(cluster)
        cluster_infos.append(core.ClusterInfo(
            cluster_id=i,
            items=cluster,
            selected_primary=primary_idx,
            confidence=core.cluster_confidence(cluster),
        ))
    
    records = core.build_proposed_records(cluster_infos)
    t0 = time.perf_counter()
    # Simulate applying merges by tracking which items to remove
    merged_ids = set()
    for rec in records:
        merged_ids.update(id(m) for m in rec.merged)
    merged_items = [it for it in items if id(it) not in merged_ids]
    t1 = time.perf_counter()
    print(f"  Merge plan time: {t1-t0:.3f}s")
    print(f"  Before: {len(items)} items")
    print(f"  After: {len(merged_items)} items")
    print(f"  Reduction: {len(items)-len(merged_items)} ({100*(len(items)-len(merged_items))/len(items):.1f}%)")
    return merged_items


def test_undo_manager(items, raw_data):
    print("\n[5] Undo Manager Stress")
    um = UndoManager()
    t0 = time.perf_counter()
    um.push(items, raw_data, "initial load")
    # Simulate 10 edits
    for i in range(10):
        dup_items = items[:]
        dup_raw = copy.deepcopy(raw_data)
        um.push(dup_items, dup_raw, f"edit {i+1}")
    t1 = time.perf_counter()
    print(f"  10 snapshots: {t1-t0:.3f}s")
    print(f"  Stack size: {len(um._stack)}")
    print(f"  Can undo: {um.can_undo()}")
    print(f"  Can redo: {um.can_redo()}")
    
    t0 = time.perf_counter()
    for _ in range(5):
        um.undo()
    t1 = time.perf_counter()
    print(f"  5 undo ops: {t1-t0:.3f}s")
    print(f"  Can redo: {um.can_redo()}")
    
    t0 = time.perf_counter()
    for _ in range(5):
        um.redo()
    t1 = time.perf_counter()
    print(f"  5 redo ops: {t1-t0:.3f}s")


def test_health_audit(items):
    print("\n[6] Health Audit (GUI logic)")
    import re
    weak = []
    empty = []
    reuse_map = {}
    no_totp = []
    
    KNOWN_2FA = [
        "google.com", "github.com", "amazon.com", "apple.com", "microsoft.com",
        "facebook.com", "twitter.com", "linkedin.com", "discord.com", "slack.com",
        "stripe.com", "shopify.com", "coinbase.com", "binance.com", "bankofamerica.com",
        "chase.com", "schwab.com", "fidelity.com", "healthcare.gov", "mychart.org"
    ]
    
    WEAK_RE = re.compile(r"^(password|123456|qwerty|abc123|letmein|welcome|admin|login|passw0rd|111111|123123|sunshine|princess|dragon|football|baseball|monkey|master|shadow|superman|michael|mustang|access|love|pussy|696969|qwertyuiop|123321|password123|1234567890|admin123)", re.IGNORECASE)
    
    t0 = time.perf_counter()
    for item in items:
        if item.is_login() and item.login:
            pw = item.login.password or ""
            if pw:
                if len(pw) < 8 or WEAK_RE.search(pw):
                    weak.append((item.name, pw))
                reuse_map.setdefault(pw, []).append(item)
            else:
                empty.append(item)
            
            uris = item.login.uris or []
            has_2fa = item.login.totp
            if not has_2fa:
                for u in uris:
                    domain = u.uri or ""
                    for prov in KNOWN_2FA:
                        if prov in domain:
                            no_totp.append((item.name, domain))
                            break
    
    reused = [(pw, len(group)) for pw, group in reuse_map.items() if len(group) > 1]
    t1 = time.perf_counter()
    
    print(f"  Scan time: {t1-t0:.3f}s")
    print(f"  Weak passwords: {len(weak)}")
    print(f"  Empty passwords: {len(empty)}")
    print(f"  Reused passwords: {len(reused)} clusters")
    print(f"  Missing 2FA: {len(no_totp)}")
    if reused:
        max_reuse = max(reused, key=lambda x: x[1])
        print(f"  Most reused: {max_reuse[1]} items sharing same password")


def test_search(items):
    print("\n[7] Search Stress")
    queries = ["google", "bank", "password", "ssh", "visa", "admin", "note", "work", "john", "com"]
    t0 = time.perf_counter()
    for q in queries:
        terms = core.parse_search_query(q)
        matches = [it for it in items if core.item_matches_terms(it, terms)]
    t1 = time.perf_counter()
    print(f"  10 queries across {len(items)} items: {t1-t0:.3f}s")
    print(f"  Avg query: {(t1-t0)/10*1000:.1f}ms")


def test_memory():
    print("\n[8] Memory / Save Roundtrip")
    import tempfile
    items, raw_data = core.load_vault(VAULT_PATH)
    tmp = Path(tempfile.mktemp(suffix=".json"))
    t0 = time.perf_counter()
    core.save_vault(tmp, items, raw_data)
    t1 = time.perf_counter()
    print(f"  Save time: {t1-t0:.3f}s")
    size_mb = tmp.stat().st_size / 1024 / 1024
    print(f"  Output size: {size_mb:.2f} MB")
    tmp.unlink()


def main():
    print("=" * 60)
    print("BITMERGER STRESS TEST — 5000+ ITEM VAULT")
    print("=" * 60)
    
    vault = test_load()
    raw_data, items = test_engine_parse(vault)
    clusters = test_dedup_analysis(items)
    merged = test_merge_simulation(items, raw_data, clusters)
    test_undo_manager(items, raw_data)
    test_health_audit(items)
    test_search(items)
    test_memory()
    
    print("\n" + "=" * 60)
    print("ALL STRESS TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
