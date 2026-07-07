from __future__ import annotations

from typing import Any


def format_rpc_error(payload: Any) -> str:
    """Turn a JSON-RPC error payload into a short human-readable message."""
    if isinstance(payload, dict):
        if "error" in payload and isinstance(payload["error"], dict):
            err = payload["error"]
            message = str(err.get("message") or "Request failed")
            data = err.get("data")
            if data is None:
                return message
            if isinstance(data, str):
                return f"{message}: {data}"
            return f"{message}: {data!s}"
        return str(payload)
    text = str(payload)
    if text.startswith("{") and "'error'" in text:
        try:
            import ast

            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return format_rpc_error(parsed)
    return text


class SubstrateRequestException(Exception):
    def __init__(self, payload: Any):
        self.payload = payload if isinstance(payload, dict) else None
        super().__init__(format_rpc_error(payload))


class MaxRetriesExceeded(SubstrateRequestException):
    pass


class StateDiscardedError(SubstrateRequestException):
    def __init__(self, block_hash: str):
        self.block_hash = block_hash
        message = (
            f"State discarded for {block_hash}. This indicates the block is too old, and you should instead "
            f"make this request using an archive node."
        )
        super().__init__(message)


class StorageFunctionNotFound(ValueError):
    pass


class BlockNotFound(Exception):
    pass
