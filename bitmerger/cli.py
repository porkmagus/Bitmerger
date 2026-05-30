"""
Bitmerger CLI: deduplication and batch rename commands.

Backward-compatible: ``python bw_dedup.py vault.json`` still routes to dedup.
"""

import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text

from .core import (
    BwItem, ClusterInfo, MergeRecord,
    normalize_domain, clean_uri,
    find_duplicates_by_type, cluster_confidence, pick_primary,
    merge_items, build_proposed_records,
    create_backup, create_merge_log, generate_html_report,
    parse_search_query, filter_items_by_name, create_rename_log,
    load_vault, save_vault,
)

console = Console()


def _show_duplicate_report(clusters: List[List[BwItem]], max_display: int = 50) -> None:
    display = clusters[:max_display]
    type_names = {1: "Login", 2: "Note", 3: "Card", 4: "Identity", 5: "SSH"}
    table = Table(title=f"Duplicate Clusters (showing {len(display)} of {len(clusters)})", show_lines=True)
    table.add_column("Cluster", style="cyan", no_wrap=True)
    table.add_column("Type", style="yellow")
    table.add_column("Count")
    table.add_column("Names")
    table.add_column("Confidence", style="green")
    table.add_column("Key", style="dim")

    for idx, cluster in enumerate(display, 1):
        first = cluster[0]
        tname = type_names.get(first.type, "Other")
        names = [c.name for c in cluster]
        conf = cluster_confidence(cluster)
        conf_style = "green" if conf >= 0.95 else "yellow" if conf >= 0.85 else "red"

        key = ""
        if first.is_login():
            key = (first.login.username or "") if first.login else ""
        elif first.is_card():
            key = first.get_card_fingerprint() or ""
        elif first.is_identity():
            key = first.identity.get("email", "") if first.identity else ""
        elif first.is_ssh_key():
            key = (first.sshKey.keyFingerprint or "") if first.sshKey else ""

        table.add_row(
            f"#{idx}", tname, str(len(cluster)), "\n".join(names),
            f"[{conf_style}]{conf:.0%}[/{conf_style}]", key
        )
    console.print(table)
    if len(clusters) > max_display:
        console.print(f"[dim]... and {len(clusters) - max_display} more clusters")


@click.group()
def cli() -> None:
    """Bitmerger: Bitwarden vault deduplication and batch management."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output JSON path.")
@click.option("-t", "--threshold", type=float, default=0.85, show_default=True, help="Similarity threshold.")
@click.option("--review", is_flag=True, help="Interactive review mode (prompt for each cluster).")
@click.option("--dry-run", is_flag=True, help="Preview + generate report without writing output.")
@click.option("--report-only", is_flag=True, help="Analyze + generate report only. No merge, no output.")
@click.option("--fast", is_flag=True, help="Skip expensive fuzzy matching for speed.")
@click.option("--types", type=str, default="1,2,3,4,5", help="Comma-separated item types to deduplicate.")
@click.option("--no-backup", is_flag=True, help="Skip creating a backup of the original file.")
@click.option("--confidence", type=float, default=None, help="Only auto-merge clusters above this confidence (0.0-1.0).")
def dedup(
    input_file: str,
    output: Optional[str],
    threshold: float,
    review: bool,
    dry_run: bool,
    report_only: bool,
    fast: bool,
    types: str,
    no_backup: bool,
    confidence: Optional[float],
) -> None:
    """Deduplicate a Bitwarden vault export."""
    input_path = Path(input_file)
    output_path = Path(output) if output else input_path.with_suffix(".dedup.json")
    report_path = input_path.with_suffix(".report.html")
    target_types = set(int(t.strip()) for t in types.split(",") if t.strip().isdigit())

    t0 = time.time()
    console.print(f"[bold green]Loading[/] {input_path}")
    all_items, data = load_vault(input_path)

    type_names = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH Keys"}
    counts_str = ", ".join(f"{type_names.get(t, f'Type{t}')}: {sum(1 for i in all_items if i.type == t)}" for t in sorted(target_types))
    console.print(f"[bold]Total items:[/] {len(all_items)} [dim]({counts_str})")
    console.print(f"[bold]Deduplicating types:[/] {sorted(target_types)}")
    console.print(f"[dim](loaded in {time.time() - t0:.2f}s)")

    dedup_items: list[BwItem] = [i for i in all_items if i.type in target_types]
    pass_through: list[BwItem] = [i for i in all_items if i.type not in target_types]

    if not dedup_items:
        console.print("[yellow]No items of target types found. Nothing to do.")
        return

    clusters, total_comp = find_duplicates_by_type(dedup_items, threshold=threshold, fast=fast)
    console.print(f"[dim]Total similarity comparisons: {total_comp:,}")
    console.print(f"[bold magenta]Found {len(clusters)} duplicate clusters[/] (threshold={threshold})")

    if not clusters:
        console.print("[green]No duplicates found. Nothing to do.")
        return

    _show_duplicate_report(clusters)

    # Build cluster info
    cluster_infos: list[ClusterInfo] = []
    for idx, cluster in enumerate(clusters):
        best_idx = pick_primary(cluster)
        conf = cluster_confidence(cluster)
        cluster_infos.append(ClusterInfo(
            cluster_id=idx,
            items=cluster,
            selected_primary=best_idx,
            confidence=conf,
        ))

    # Confidence filtering
    high_conf = [ci for ci in cluster_infos if ci.confidence >= 0.95]
    med_conf = [ci for ci in cluster_infos if 0.85 <= ci.confidence < 0.95]
    low_conf = [ci for ci in cluster_infos if ci.confidence < 0.85]

    console.print("\n[bold]Confidence Distribution[/]")
    console.print(f"  [green]High (>=95%):[/] {len(high_conf)} clusters — auto-merge safe")
    console.print(f"  [yellow]Medium (85-95%):[/] {len(med_conf)} clusters — review recommended")
    console.print(f"  [red]Low (<85%):[/] {len(low_conf)} clusters — review strongly recommended")

    # Interactive review mode
    if review:
        for ci in cluster_infos:
            primary = ci.primary()
            console.print(f"\n[bold]Cluster #{ci.cluster_id + 1}[/] [dim](confidence: {ci.confidence:.0%})[/]")
            for i, item in enumerate(ci.items):
                marker = "🟢" if i == ci.selected_primary else "🔴"
                console.print(f"  {marker} {item.name}")
            if ci.confidence >= 0.95:
                default = "y"
            else:
                default = "n"
            choice = Prompt.ask(
                f"Merge into [bold]{primary.name}[/]?",
                default=default,
                choices=["y", "n", "s"],
                show_choices=True,
            )
            if choice == "y":
                ci.skipped = False
            elif choice == "s":
                ci.skipped = True
            else:
                # Pick different primary
                choices = [f"{i+1}. {c.name}" for i, c in enumerate(ci.items)]
                for ch in choices:
                    console.print(f"    {ch}")
                new_idx = Prompt.ask(
                    "Pick primary",
                    default="1",
                    choices=[str(i+1) for i in range(len(ci.items))]
                )
                ci.selected_primary = int(new_idx) - 1
                ci.skipped = False

    # Apply confidence filter if specified
    if confidence is not None:
        approved: list[ClusterInfo] = [ci for ci in cluster_infos if ci.confidence >= confidence and not ci.skipped]
        skipped: list[ClusterInfo] = [ci for ci in cluster_infos if ci.confidence < confidence or ci.skipped]
        for ci in skipped:
            ci.skipped = True
        console.print(f"\n[bold]Confidence Filter Applied:[/] {confidence:.0%}")
        console.print(f"  Approved: {len(approved)} clusters")
        console.print(f"  Skipped: {len(skipped)} clusters")

    # Determine mode
    if report_only or dry_run:
        proposed_records = build_proposed_records(cluster_infos)
        report_stats: Dict[str, int] = {
            "original": len(all_items),
            "final": len(all_items) - len(proposed_records),
            "merged": len(proposed_records),
            "clusters": len(clusters),
        }
        console.print("\n[bold]Summary[/]")
        console.print(f"  Original items: {report_stats['original']}")
        console.print(f"  Would merge: {report_stats['merged']} clusters")
        console.print(f"  Total time: {time.time() - t0:.2f}s")
        if dry_run:
            console.print("\n[yellow]Dry run — no files written[/]")
        else:
            console.print("\n[yellow]Report only — no output or backup written[/]")
        generate_html_report(
            records=proposed_records,
            stats=report_stats,
            threshold=threshold,
            filename=input_path.name,
            output_path=report_path,
        )
        return

    # Build merge plan (real merge)
    merged_away_ids: set[str] = set()
    merge_records: List[MergeRecord] = []

    for ci in cluster_infos:
        if ci.skipped:
            continue
        primary = ci.items[ci.selected_primary]
        all_new_uris: List[str] = []
        all_backfilled: Dict[str, Any] = {}

        for i, c in enumerate(ci.items):
            if i != ci.selected_primary:
                primary, backfilled = merge_items(primary, c)
                merged_away_ids.add(c.id)
                for k, v in backfilled.items():
                    if k == "uris":
                        if c.login:
                            all_new_uris.extend([clean_uri(u.uri) for u in c.login.uris])
                    else:
                        from .core import _accumulate_backfill
                        _accumulate_backfill(all_backfilled, {k: v})

        seen: set[str] = {clean_uri(u.uri).lower() for u in primary.login.uris} if primary.login else set()
        unique_new: list[str] = []
        for u_str in all_new_uris:
            cu_cleaned: str = clean_uri(u_str).lower()
            if cu_cleaned not in seen:
                unique_new.append(u_str)
                seen.add(cu_cleaned)

        merge_records.append(
            MergeRecord(
                cluster_id=ci.cluster_id + 1,
                primary=primary,
                merged=ci.items,
                new_uris=unique_new,
                backfilled=all_backfilled,
            )
        )

    kept: list[BwItem] = [i for i in dedup_items if i.id not in merged_away_ids]
    final_items: list[BwItem] = kept + pass_through

    out_data = dict(data)
    out_data["items"] = [i.to_dict() for i in final_items]

    final_stats: Dict[str, int] = {
        "original": len(all_items),
        "final": len(final_items),
        "merged": len(merged_away_ids),
        "clusters": len(clusters),
    }

    console.print("\n[bold]Summary[/]")
    console.print(f"  Original items: {final_stats['original']}")
    console.print(f"  Merged away: {final_stats['merged']}")
    console.print(f"  Final items: {final_stats['final']}")
    console.print(f"  Total time: {time.time() - t0:.2f}s")

    if not no_backup:
        backup = create_backup(input_path)
        console.print(f"\n[dim]Backup created: {backup}")

    with open(output_path, "w", encoding="utf-8") as f:
        import json
        json.dump(out_data, f, indent=2, ensure_ascii=False)
    console.print(f"\n[bold green]Wrote clean export to[/] {output_path}")

    if merge_records:
        log_path = create_merge_log(merge_records, output_path)
        console.print(f"[dim]Merge log: {log_path}")

    generate_html_report(
        records=merge_records,
        stats=final_stats,
        threshold=threshold,
        filename=input_path.name,
        output_path=report_path,
    )

    console.print(Panel(
        Text.assemble(
            ("Cleaned ", "bold white"),
            (f"{final_stats['merged']}", "bold green"),
            (" duplicates from ", "bold white"),
            (f"{final_stats['original']}", "bold blue"),
            (" items.", "bold white"),
            ("\n", ""),
            ("Import back into Bitwarden via: Tools → Import Data → Bitwarden (json)", "dim"),
        ),
        title="🔐 Bitmerger Complete",
        border_style="green"
    ))


@cli.command(name="batch-rename")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output JSON path.")
@click.option("--search", required=True, help="Search query. Use + for OR: google+mail.google")
@click.option("--replace", required=True, help="New name for all matched items")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--no-backup", is_flag=True, help="Skip creating a backup of the original file")
@click.option("--types", type=str, default="1,2,3,4,5", help="Comma-separated item types to search")
@click.option("--dry-run", is_flag=True, help="Preview matches without writing output")
def batch_rename(
    input_file: str,
    output: Optional[str],
    search: str,
    replace: str,
    yes: bool,
    no_backup: bool,
    types: str,
    dry_run: bool,
) -> None:
    """Batch rename vault items by name search."""
    input_path = Path(input_file)
    output_path = Path(output) if output else input_path.with_suffix(".renamed.json")
    target_types = set(int(t.strip()) for t in types.split(",") if t.strip().isdigit())

    t0 = time.time()
    console.print(f"[bold green]Loading[/] {input_path}")
    all_items, data = load_vault(input_path)

    type_names = {1: "Logins", 2: "Notes", 3: "Cards", 4: "Identities", 5: "SSH Keys"}
    counts_str = ", ".join(f"{type_names.get(t, f'Type{t}')}: {sum(1 for i in all_items if i.type == t)}" for t in sorted(target_types))
    console.print(f"[bold]Total items:[/] {len(all_items)} [dim]({counts_str})")
    console.print(f"[dim](loaded in {time.time() - t0:.2f}s)")

    terms = parse_search_query(search)
    console.print(f"[bold]Search terms:[/] {terms}")

    matches = filter_items_by_name(all_items, terms, target_types)
    if not matches:
        console.print("[yellow]No items matched the search query. Nothing to do.")
        return

    # Show preview
    type_names = {1: "Login", 2: "Note", 3: "Card", 4: "Identity", 5: "SSH"}
    table = Table(title=f"Matched Items ({len(matches)} found)", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Type", style="yellow")
    table.add_column("Current Name")
    table.add_column("Username", style="cyan")
    table.add_column("Domain", style="green")
    for item in matches:
        tname = type_names.get(item.type, "Other")
        username = ""
        domain = ""
        if item.login:
            username = item.login.username or ""
            if item.login.uris:
                domain = normalize_domain(item.login.uris[0].uri) or ""
        table.add_row(item.id, tname, item.name, username, domain)
    console.print(table)

    if not yes:
        choice = Prompt.ask(
            f"Rename {len(matches)} item(s) to [bold]{replace}[/]?",
            default="n",
            choices=["y", "n"],
            show_choices=True,
        )
        if choice != "y":
            console.print("[yellow]Cancelled.")
            return

    if dry_run:
        console.print("[yellow]Dry run — no files written.")
        return

    match_ids: set[int] = {id(m) for m in matches}
    renamed: list[tuple[str, str, str]] = []
    for item in all_items:
        if id(item) in match_ids:
            old_name = item.name
            item.name = replace
            renamed.append((item.id, old_name, replace))

    save_vault(output_path, all_items, data)

    if not no_backup:
        backup = create_backup(input_path)
        console.print(f"[dim]Backup created: {backup}")

    console.print(f"[bold green]Wrote renamed export to[/] {output_path}")

    if renamed:
        log_path = create_rename_log(renamed, output_path)
        console.print(f"[dim]Rename log: {log_path}")

    console.print(Panel(
        Text.assemble(
            ("Renamed ", "bold white"),
            (f"{len(renamed)}", "bold green"),
            (" items to ", "bold white"),
            (f"{replace}", "bold blue"),
            (".", "bold white"),
        ),
        title="🔐 Bitmerger Batch Rename",
        border_style="green"
    ))


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] not in ("dedup", "batch-rename", "--help", "-h"):
        sys.argv.insert(1, "dedup")
    cli()
