"""`subtensor view`: HTML dashboard export."""

from __future__ import annotations

import asyncio
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional

import typer

from ..._generated import runtime_apis as api
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Visual dashboard views.")


@app.command("dashboard")
@with_globals
def dashboard(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
    save_path: Optional[Path] = typer.Option(None, "--save-path", help="Write HTML to this path."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open in the default browser."),
):
    """Generate a simple HTML wallet/subnet dashboard."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)

    async def _gather(client):
        balance, stakes, subnets, metagraphs = await asyncio.gather(
            client.balances.get(owner),
            client.read("stake_for_coldkey", coldkey_ss58=owner),
            client.subnets.all(),
            client.runtime(api.SubnetInfoRuntimeApi.get_all_metagraphs, []),
        )
        return {
            "coldkey": owner,
            "balance_tao": balance.tao,
            "stakes": [
                {
                    "netuid": s.netuid,
                    "hotkey": s.hotkey,
                    "stake": str(s.stake),
                }
                for s in stakes
            ],
            "subnets": len(subnets),
            "metagraphs": len(metagraphs or []),
        }

    data = app_ctx.run(_gather)
    html = _render_html(data)
    if save_path:
        save_path.write_text(html)
        app_ctx.output.detail("dashboard saved", {"path": str(save_path)})
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as handle:
            handle.write(html)
            path = handle.name
        app_ctx.output.detail("dashboard", {"path": path})
        if open_browser and not app_ctx.output.json_mode:
            webbrowser.open(f"file://{path}")


def _render_html(data: dict) -> str:
    stakes_rows = "".join(
        f"<tr><td>{s['netuid']}</td><td>{s['hotkey']}</td><td>{s['stake']}</td></tr>"
        for s in data["stakes"]
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>subtensor dashboard</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; }}
</style></head><body>
<h1>subtensor dashboard</h1>
<p><strong>Coldkey:</strong> {data['coldkey']}</p>
<p><strong>Free balance:</strong> {data['balance_tao']:.4f} τ</p>
<p><strong>Subnets:</strong> {data['subnets']}</p>
<h2>Stake positions</h2>
<table><tr><th>netuid</th><th>hotkey</th><th>stake</th></tr>{stakes_rows}</table>
</body></html>"""
