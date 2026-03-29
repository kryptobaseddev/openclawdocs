"""CLI entry point for openclaw-docs."""

from __future__ import annotations

from pathlib import Path

import click

from openclaw_docs import display
from openclaw_docs.config import get_data_dir, get_db_path, get_topics_dir
from openclaw_docs.parser import parse_full_content
from openclaw_docs.search import SearchEngine
from openclaw_docs.storage import DocsStorage
from openclaw_docs.sync import DocsSyncer


def _require_synced(storage: DocsStorage) -> None:
    """Exit with message if no sync has been done."""
    if storage.count_topics() == 0:
        click.echo("No local docs. Run `openclaw-docs sync` first.")
        raise SystemExit(1)


@click.group()
@click.option(
    "--data-dir",
    type=click.Path(),
    envvar="OPENCLAW_DOCS_DATA_DIR",
    default=None,
    help="Override data directory path",
)
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
@click.pass_context
def sync(ctx: click.Context, force: bool) -> None:
    """Download/update documentation from docs.openclaw.ai."""
    storage: DocsStorage = ctx.obj["storage"]
    syncer = DocsSyncer(storage)
    click.echo("Syncing documentation...")
    report = syncer.sync(force=force)
    click.echo(display.fmt_sync_report(report))


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--verbose", "-v", is_flag=True, help="Include snippets and sections")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int, verbose: bool, category: str | None) -> None:
    """Search documentation. Returns titles + paths + scores."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    topics_dir = ctx.obj["data_dir"] / "topics" if "data_dir" in ctx.obj else get_topics_dir()
    engine = SearchEngine(storage, topics_dir)
    results = engine.search(query, limit=limit, category=category, include_snippets=verbose)
    click.echo(display.fmt_search_results(results, verbose=verbose))


@cli.command()
@click.argument("topic_path")
@click.option("--full", is_flag=True, help="Show complete content instead of summary")
@click.option("--section", "-s", default=None, help="Show only a specific section by name (fuzzy match)")
@click.pass_context
def show(ctx: click.Context, topic_path: str, full: bool, section: str | None) -> None:
    """Display a topic. Default: summary + section list.

    Progressive disclosure levels:
      (default)    Summary + section list (~150 tokens)
      --section X  Just one section (~200-500 tokens)
      --full       Complete content (varies)
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
                click.echo(f"Topic '{topic_path}' not found. Did you mean:")
                for m, score, _idx in matches:
                    click.echo(f"  {m}")
            else:
                click.echo(f"Topic '{topic_path}' not found.")
        else:
            click.echo(f"Topic '{topic_path}' not found.")
        raise SystemExit(1)

    topics_dir = ctx.obj["data_dir"] / "topics" if "data_dir" in ctx.obj else get_topics_dir()

    if section:
        content = storage.get_topic_content(topic_path, topics_dir)
        if content:
            click.echo(display.fmt_topic_section(topic, content, section))
        else:
            click.echo("Content not available.")
            raise SystemExit(1)
    elif full:
        content = storage.get_topic_content(topic_path, topics_dir)
        if content:
            click.echo(display.fmt_topic_full(topic, content))
        else:
            click.echo(display.fmt_topic_summary(topic))
            click.echo("\n(Content file not found — showing summary only)")
    else:
        click.echo(display.fmt_topic_summary(topic))


@cli.command(name="list")
@click.option("--category", "-c", default=None, help="List topics within a category")
@click.pass_context
def list_cmd(ctx: click.Context, category: str | None) -> None:
    """List categories or topics within a category."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    if category:
        topics = storage.list_topics(category=category)
        click.echo(display.fmt_topic_list(topics))
    else:
        categories = storage.list_categories()
        click.echo(display.fmt_categories(categories))


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show sync status and doc statistics."""
    storage: DocsStorage = ctx.obj["storage"]
    data_dir = ctx.obj["data_dir"]
    stat = storage.get_status(data_dir)
    click.echo(display.fmt_status(stat))


@cli.command()
@click.pass_context
def diff(ctx: click.Context) -> None:
    """Compare local docs against remote for changes."""
    storage: DocsStorage = ctx.obj["storage"]
    _require_synced(storage)

    click.echo("Checking remote...")
    syncer = DocsSyncer(storage)
    _llms_txt, llms_full = syncer.check_remote()

    if not llms_full:
        click.echo("Failed to fetch remote docs.")
        raise SystemExit(1)

    remote_topics = parse_full_content(llms_full)
    remote_map = {t.path: t.content_hash for t in remote_topics}

    # Compare against local
    local_topics = storage.list_topics()
    local_map = {t["path"]: storage.get_topic_hash(t["path"]) for t in local_topics}

    added = [p for p in remote_map if p not in local_map]
    removed = [p for p in local_map if p not in remote_map]
    changed = [
        p for p in remote_map
        if p in local_map and remote_map[p] != local_map[p]
    ]

    click.echo(display.fmt_diff(added, changed, removed))
