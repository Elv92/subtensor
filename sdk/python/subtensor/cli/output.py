"""Rendering: one object that speaks either to humans or to scripts.

Every command routes all output through an ``Output`` instance instead of printing
directly, so ``--json`` and ``--quiet`` work uniformly everywhere and a machine
consumer never has to scrape a rich table.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..intents import Plan
from ..result import ExtrinsicResult


class Output:
    def __init__(self, json_mode: bool = False, quiet: bool = False):
        self.json_mode = json_mode
        self.quiet = quiet
        self._out = Console()
        self._err = Console(stderr=True)

    def _json(self, payload: Any) -> None:
        self._out.print_json(_json.dumps(payload, default=str))

    def message(self, text: str) -> None:
        """Informational chatter. Suppressed by --quiet and in --json mode."""
        if not self.quiet and not self.json_mode:
            self._out.print(text)

    def value(self, payload: Any) -> None:
        """Emit an arbitrary already-JSON-friendly value (used by generic query)."""
        if self.json_mode:
            self._json(payload)
        else:
            self._out.print(payload)

    def error(self, text: str) -> None:
        if self.json_mode:
            self._err.print_json(_json.dumps({"error": text}))
        else:
            self._err.print(f"[red]error:[/red] {text}")

    def detail(self, title: Optional[str], fields: dict[str, Any]) -> None:
        """A single record as key/value pairs (human) or an object (json)."""
        if self.json_mode:
            self._json(fields)
            return
        if title:
            self._out.print(f"[bold]{title}[/bold]")
        width = max((len(k) for k in fields), default=0)
        for key, value in fields.items():
            self._out.print(f"  {key.rjust(width)}: {value}")

    def table(
        self,
        title: str,
        columns: list[str],
        rows: list[list[Any]],
        records: Optional[list[dict]] = None,
    ) -> None:
        """A collection as a table (human) or a list of objects (json).

        ``records`` supplies the JSON shape; when omitted it is derived by zipping
        ``columns`` with each row.
        """
        if self.json_mode:
            self._json(
                records if records is not None else [dict(zip(columns, row)) for row in rows]
            )
            return
        table = Table(title=title)
        for column in columns:
            table.add_column(column)
        for row in rows:
            table.add_row(*(str(cell) for cell in row))
        self._out.print(table)

    def tree(
        self,
        title: str,
        nodes: list[tuple[str, list[str]]],
        records: Optional[list[dict]] = None,
    ) -> None:
        """Render a two-level grouping as a tree (human) or list of objects (json).

        ``nodes`` is a list of ``(branch_label, [leaf_label, ...])`` pairs; rich
        markup in the labels is honoured. ``records`` supplies the JSON shape.
        """
        if self.json_mode:
            self._json(records if records is not None else [])
            return
        root = Tree(f"[bold]{title}[/bold]")
        for branch_label, leaves in nodes:
            branch = root.add(branch_label)
            for leaf in leaves:
                branch.add(leaf)
        self._out.print(root)

    @staticmethod
    def _wallet_node(
        name: str,
        ss58: str | None,
        *,
        name_style: str,
        count: int | None = None,
        crypto_type: str | None = None,
    ) -> Text:
        node = Text()
        node.append(name, style=name_style)
        if crypto_type:
            node.append(f"  ({crypto_type})", style="dim magenta")
        if count:
            suffix = "hotkey" if count == 1 else "hotkeys"
            node.append(f"  ({count} {suffix})", style="dim")
        if ss58:
            node.append("\n")
            node.append(ss58, style="dim cyan")
        elif ss58 is None:
            node.append("\n")
            node.append("—", style="dim red")
        return node

    def wallet_list(self, path: str, records: list[dict[str, Any]]) -> None:
        """Render coldkeys and hotkeys with aligned names and ss58 addresses."""
        if self.json_mode:
            self._json(records)
            return

        display_path = str(Path(path).expanduser())
        home = str(Path.home())
        if display_path.startswith(home):
            display_path = "~" + display_path[len(home) :]

        self._out.print("[bold]Wallets[/bold]")
        self._out.print()

        root = Tree(f"[dim italic]{display_path}[/dim italic]", guide_style="bright_black")
        for ck in records:
            hotkeys = ck.get("hotkeys", [])
            branch = root.add(
                self._wallet_node(
                    ck["coldkey"],
                    ck.get("ss58"),
                    name_style="bold white",
                    count=len(hotkeys) or None,
                    crypto_type=ck.get("crypto_type"),
                )
            )
            if not hotkeys:
                branch.add(Text("no hotkeys", style="dim italic"))
                continue
            for hk in hotkeys:
                branch.add(
                    self._wallet_node(
                        hk["name"],
                        hk.get("ss58"),
                        name_style="green",
                        crypto_type=hk.get("crypto_type"),
                    )
                )

        self._out.print(root)

        total_coldkeys = len(records)
        total_hotkeys = sum(len(ck.get("hotkeys", [])) for ck in records)
        self._out.print()
        self._out.print(f"[dim]{total_coldkeys} coldkeys  ·  {total_hotkeys} hotkeys[/dim]")

    def plan(self, plan: Plan) -> None:
        """Render a dry-run plan (fee, effects, warnings, policy)."""
        if self.json_mode:
            self._json(plan.to_dict())
            return
        self._out.print(f"[bold]dry run:[/bold] {plan.summary}")
        self._out.print(f"  signer: {plan.signer} ({plan.signer_address})")
        if plan.fee is not None:
            self._out.print(f"  est. fee: {plan.fee}")
        for effect in plan.effects:
            self._out.print(f"  effect: {effect}")
        for warning in plan.warnings:
            self._out.print(f"  [yellow]warning:[/yellow] {warning}")
        for violation in plan.violations:
            self._out.print(f"  [red]policy:[/red] {violation}")
        if not plan.ok:
            self._out.print("  [red]blocked by policy[/red]")

    def result(self, result: ExtrinsicResult, success_message: str) -> bool:
        """Render the outcome of a submitted extrinsic. Returns ``result.success``.

        JSON mode emits the canonical ``ExtrinsicResult.to_dict()`` (including
        ``data`` and the structured, coded ``error``) so machine consumers get the
        full shape rather than a re-implemented subset.
        """
        if self.json_mode:
            self._json(result.to_dict())
        elif result.success:
            self._out.print(f"[green]{success_message}[/green]")
            if result.fee is not None:
                self._out.print(f"  fee: {result.fee}")
            if result.block_hash:
                self._out.print(f"  block: {result.block_hash}")
            for key, value in result.data.items():
                self._out.print(f"  {key}: {value}")
        else:
            self._err.print(f"[red]failed:[/red] {result.message}")
        return result.success
