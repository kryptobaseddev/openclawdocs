"""CLI entry point for openclaw-docs.

All commands support --json for structured agent output.

Exit codes:
  0 — success (results found, sync complete, etc.)
  1 — no results or not found (search returned nothing, topic doesn't exist)
  2 — error (network failure, no sync, invalid state)
"""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import click

from openclaw_docs import display
from openclaw_docs.config import get_data_dir, get_db_path, get_topics_dir
from openclaw_docs.parser import parse_full_content
from openclaw_docs.search import SearchEngine
from openclaw_docs.storage import DocsStorage
from openclaw_docs.sync import DocsSyncer


EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_ERROR = 2


def _require_synced(storage: DocsStorage) -> None:
    if storage.count_topics() == 0:
        click.echo("No local docs. Run `ocdocs sync` first.")
        raise SystemExit(EXIT_ERROR)


def _topics_dir(ctx: click.Context) -> Path:
    return ctx.obj["data_dir"] / "topics"


def _out(data: object, use_json: bool) -> None:
    """Output data as JSON or let caller handle text."""
    if use_json:
        click.echo(json_mod.dumps(data, default=str))


def _freshness_payload(storage: DocsStorage, data_dir: Path) -> dict:
    stat = storage.get_status(data_dir)
    return {
        "last_sync": stat.last_sync,
        "age_seconds": stat.age_seconds,
        "stale_after_hours": stat.stale_after_hours,
        "is_stale": stat.is_stale,
    }


@click.group()
@click.option("--data-dir", type=click.Path(), envvar="OPENCLAW_DOCS_DATA_DIR",
              default=None, help="Override data directory path")
@click.pass_context
def cli(ctx: click.Context, data_dir: str | None) -> None:
    """OpenClaw documentation tool for LLM agents."""
    ctx.ensure_object(dict)
    data = Path(data_dir) if data_dir else get_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    db_path = data / "docs.db" if data_dir else get_db_path()
    ctx.obj["data_dir"] = data
    ctx.obj["storage"] = DocsStorage(db_path)


@cli.command()
@click.option("--force", is_flag=True, help="Force re-download ignoring cache")
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.pass_context
def sync(ctx: click.Context, force: bool, use_json: bool) -> None:
    """Download/update documentation from docs.openclaw.ai."""
    storage: DocsStorage = ctx.obj["storage"]
    syncer = DocsSyncer(storage)
    if not use_json:
        click.echo("Syncing documentation...")
    report = syncer.sync(force=force)
    if use_json:
        _out({"type": "sync", "added": report.added, "updated": report.updated,
              "removed": report.removed, "unchanged": report.unchanged,
              "total": report.total, "errors": report.errors,
              "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
    else:
        click.echo(display.fmt_sync_report(report))


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--verbose", "-v", is_flag=True, help="Include snippets")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.option("--compact", is_flag=True, help="TSV output (path\\ttitle\\tscore)")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int, verbose: bool,
           category: str | None, use_json: bool, compact: bool) -> None:
    """Search documentation. Returns titles + paths + scores."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    engine = SearchEngine(storage, _topics_dir(ctx))
    results = engine.search(query, limit=limit, category=category, include_snippets=verbose)

    if not results:
        if use_json:
            _out({"type": "search", "query": query, "results": [], "total": 0,
                  "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
        else:
            click.echo("No results found.")
        raise SystemExit(EXIT_NOT_FOUND)

    if use_json:
        _out({"type": "search", "query": query, "results": [
            {"rank": i, "path": r.path, "title": r.title, "score": r.score,
             "snippet": r.snippet or None, "match_type": r.match_type}
            for i, r in enumerate(results, 1)
        ], "total": len(results),
        "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
    elif compact:
        for r in results:
            click.echo(f"{r.path}\t{r.title}\t{r.score:.2f}")
    else:
        click.echo(display.fmt_search_results(results, verbose=verbose))


@cli.command()
@click.argument("topic_path")
@click.option("--full", is_flag=True, help="Show complete content")
@click.option("--section", "-s", default=None, help="Show one section (fuzzy match)")
@click.option("--code-only", is_flag=True, help="Extract only code blocks")
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.pass_context
def show(ctx: click.Context, topic_path: str, full: bool, section: str | None,
         code_only: bool, use_json: bool) -> None:
    """Display a topic. Default: summary + section list.

    Progressive disclosure levels:
      (default)      Summary + section list (~150 tokens)
      --section X    Just one section (~500-1500 tokens)
      --code-only    Only code blocks from topic
      --full         Complete content (varies)
    """
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    topic = storage.get_topic(topic_path)
    if not topic:
        from rapidfuzz import fuzz, process
        titles = storage.get_all_titles()
        if titles:
            paths = [t[1] for t in titles]
            matches = process.extract(topic_path, paths, scorer=fuzz.WRatio, limit=3, score_cutoff=40.0)
            if matches:
                suggestions = [m[0] for m in matches]
                if use_json:
                    _out({"type": "error", "error": "not_found", "query": topic_path,
                          "suggestions": suggestions}, True)
                else:
                    click.echo(f"Topic '{topic_path}' not found. Did you mean:")
                    for s in suggestions:
                        click.echo(f"  {s}")
            else:
                if use_json:
                    _out({"type": "error", "error": "not_found", "query": topic_path}, True)
                else:
                    click.echo(f"Topic '{topic_path}' not found.")
        raise SystemExit(EXIT_NOT_FOUND)

    topics_dir = _topics_dir(ctx)
    sections_list = json_mod.loads(topic["sections"]) if isinstance(topic["sections"], str) else topic["sections"]

    if use_json:
        content = storage.get_topic_content(topic_path, topics_dir)
        related = display.extract_related(content, topic["path"]) if content else []
        data: dict = {
            "type": "show",
            "path": topic["path"],
            "title": topic["title"],
            "category": topic["category"],
            "word_count": topic["word_count"],
            "url": topic["source_url"],
            "summary": topic.get("summary", ""),
            "sections": sections_list,
            "related": related,
            "freshness": _freshness_payload(storage, ctx.obj["data_dir"]),
        }
        if code_only and content:
            from openclaw_docs.cleaner import extract_code_blocks
            data["code_blocks"] = extract_code_blocks(content)
            data["content"] = None
        elif section and content:
            # Extract section content for JSON
            data["section_query"] = section
            data["content"] = display.fmt_topic_section(topic, content, section)
        elif full and content:
            from openclaw_docs.cleaner import clean_content
            data["content"] = clean_content(content)
        else:
            data["content"] = None
        _out(data, True)
    elif code_only:
        content = storage.get_topic_content(topic_path, topics_dir)
        if content:
            click.echo(display.fmt_code_only(topic, content))
        else:
            click.echo("Content not available.")
            raise SystemExit(EXIT_ERROR)
    elif section:
        content = storage.get_topic_content(topic_path, topics_dir)
        if content:
            click.echo(display.fmt_topic_section(topic, content, section))
        else:
            click.echo("Content not available.")
            raise SystemExit(EXIT_ERROR)
    elif full:
        content = storage.get_topic_content(topic_path, topics_dir)
        if content:
            click.echo(display.fmt_topic_full(topic, content))
        else:
            click.echo(display.fmt_topic_summary(topic))
    else:
        content = storage.get_topic_content(topic_path, topics_dir)
        click.echo(display.fmt_topic_summary(topic, content))


@cli.command(name="list")
@click.option("--category", "-c", default=None, help="List topics within a category")
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.option("--compact", is_flag=True, help="One path per line")
@click.pass_context
def list_cmd(ctx: click.Context, category: str | None, use_json: bool, compact: bool) -> None:
    """List categories or topics within a category."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    if use_json:
        if category:
            topics = storage.list_topics(category=category)
            _out({"type": "list", "category": category,
                  "topics": [{"path": t["path"], "title": t["title"]} for t in topics],
                  "count": len(topics),
                  "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
        else:
            categories = storage.list_categories()
            _out({"type": "list",
                  "categories": [{"name": c, "count": n} for c, n in categories],
                  "total_topics": sum(n for _, n in categories),
                  "total_categories": len(categories),
                  "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
    elif compact:
        if category:
            for t in storage.list_topics(category=category):
                click.echo(t["path"])
        else:
            for c, n in storage.list_categories():
                click.echo(f"{c}\t{n}")
    else:
        if category:
            click.echo(display.fmt_topic_list(storage.list_topics(category=category)))
        else:
            click.echo(display.fmt_categories(storage.list_categories()))


@cli.command()
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.pass_context
def status(ctx: click.Context, use_json: bool) -> None:
    """Show sync status and doc statistics."""
    storage: DocsStorage = ctx.obj["storage"]
    stat = storage.get_status(ctx.obj["data_dir"])
    if use_json:
        _out({"type": "status", "last_sync": stat.last_sync,
              "topics": stat.total_topics, "categories": stat.total_categories,
              "index_entries": stat.index_entries, "db_size_kb": stat.db_size_bytes / 1024,
              "data_dir": stat.data_dir, "age_seconds": stat.age_seconds,
              "stale_after_hours": stat.stale_after_hours,
              "is_stale": stat.is_stale}, True)
    else:
        click.echo(display.fmt_status(stat))


@cli.command()
@click.option("--json", "use_json", is_flag=True, help="JSON output")
@click.pass_context
def diff(ctx: click.Context, use_json: bool) -> None:
    """Compare local docs against remote for changes."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    if not use_json:
        click.echo("Checking remote...")
    syncer = DocsSyncer(storage)
    _llms_txt, llms_full = syncer.check_remote()

    if not llms_full:
        if use_json:
            _out({"type": "error", "error": "fetch_failed"}, True)
        else:
            click.echo("Failed to fetch remote docs.")
        raise SystemExit(EXIT_ERROR)

    remote_topics = parse_full_content(llms_full)
    remote_map = {t.path: t.content_hash for t in remote_topics}
    local_topics = storage.list_topics()
    local_map = {t["path"]: storage.get_topic_hash(t["path"]) for t in local_topics}

    added = [p for p in remote_map if p not in local_map]
    removed = [p for p in local_map if p not in remote_map]
    changed = [p for p in remote_map if p in local_map and remote_map[p] != local_map[p]]

    if use_json:
        _out({"type": "diff", "added": added, "changed": changed, "removed": removed,
              "counts": {"added": len(added), "changed": len(changed), "removed": len(removed)},
              "up_to_date": not added and not changed and not removed,
              "freshness": _freshness_payload(storage, ctx.obj["data_dir"])}, True)
    else:
        click.echo(display.fmt_diff(added, changed, removed))
