"""WebMind Extractor — CLI interface."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich import print as rprint

from app.browser.manager import BrowserManager
from app.pipeline.orchestrator import orchestrate

app = typer.Typer(
    name="webmind",
    help="AI-powered web data extractor. Scrape any URL with a plain English query.",
    add_completion=False,
)
console = Console()


async def _run(
    url: str,
    query: str,
    content_format: Optional[str],
    export: Optional[str],
    output: Optional[Path],
    quiet: bool,
) -> dict:
    messages: list[str] = []

    async def progress_cb(msg: str):
        messages.append(msg)
        if not quiet:
            console.print(f"  [dim]→[/dim] {msg}")

    browser = BrowserManager()
    try:
        await browser.start()
        if not quiet:
            console.print(f"[green]✓[/green] Browser: [bold]{browser.browser_name}[/bold]")

        result = await orchestrate(
            browser_manager=browser,
            url=url,
            query=query,
            content_format=content_format,
            progress_callback=progress_cb,
        )
    finally:
        await browser.stop()

    return result


def _print_result(result: dict, quiet: bool):
    meta = result.get("metadata", {})
    items = result.get("items", [])
    content = result.get("generated_content", "")
    cost = result.get("cost", {})

    if not quiet:
        console.rule("[bold cyan]Results[/bold cyan]")

    # Items table
    if items:
        if items and isinstance(items[0], dict):
            keys = [k for k in items[0].keys() if not k.startswith("_")]
            table = Table(show_header=True, header_style="bold magenta", expand=True)
            for k in keys:
                table.add_column(k, overflow="fold")
            for item in items:
                table.add_row(*[str(item.get(k, "")) for k in keys])
            console.print(table)
    else:
        console.print("[yellow]No items extracted.[/yellow]")

    # Generated content
    if content:
        console.print(Panel(content, title=f"[bold]Generated Content[/bold]", border_style="green"))

    # Summary
    if not quiet:
        console.print(
            f"\n[dim]Pages: {meta.get('pages_visited', 0)} visited, "
            f"{meta.get('pages_failed', 0)} failed | "
            f"Duration: {meta.get('duration_seconds', 0)}s | "
            f"Cost: ${cost.get('total_usd', 0):.6f}[/dim]"
        )


def _export_result(result: dict, export: str, output: Optional[Path]):
    import app.output.json_export as json_mod
    import app.output.csv_export as csv_mod
    import app.output.markdown_export as md_mod

    export = export.lower()
    filename = output.name if output else None

    if export == "json":
        path = json_mod.export(result, filename)
    elif export == "csv":
        path = csv_mod.export(result, filename)
    elif export in ("md", "markdown"):
        path = md_mod.export(result, filename)
    else:
        console.print(f"[red]Unknown export format: {export}[/red]")
        return

    if path:
        console.print(f"[green]✓[/green] Saved to [bold]{path}[/bold]")
    else:
        console.print("[yellow]Nothing to export (no items/content).[/yellow]")


@app.command()
def scrape(
    url: str = typer.Argument(..., help="URL to scrape"),
    query: str = typer.Argument(..., help="Plain English query (e.g. 'product name, price, rating')"),
    format: Optional[str] = typer.Option(
        None, "--format", "-f",
        help="Generate content: product_description | comparison_article | social_media | seo_article | email_campaign | data_summary",
    ),
    export: Optional[str] = typer.Option(
        None, "--export", "-e",
        help="Export format: json | csv | md",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output file path (auto-named if omitted)",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
    json_out: bool = typer.Option(False, "--json", help="Print raw JSON result to stdout"),
):
    """Scrape a URL and extract structured data using AI."""
    if not quiet:
        console.rule("[bold cyan]WebMind Extractor[/bold cyan]")
        console.print(f"[bold]URL:[/bold]   {url}")
        console.print(f"[bold]Query:[/bold] {query}")
        if format:
            console.print(f"[bold]Format:[/bold] {format}")
        console.print()

    try:
        result = asyncio.run(_run(url, query, format, export, output, quiet))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if json_out:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_result(result, quiet)

    if export:
        _export_result(result, export, output)

    error = result.get("metadata", {}).get("error")
    if error:
        raise typer.Exit(1)


@app.command()
def version():
    """Show version info."""
    rprint("[bold]WebMind Extractor[/bold] v0.1.0")
    rprint("OpenRouter (OpenAI-compatible) | Lightpanda + Chromium fallback")


if __name__ == "__main__":
    app()
