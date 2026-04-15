from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def to_json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, BaseModel):
        return to_json_compatible(value.model_dump(mode="json", exclude_none=True))

    if is_dataclass(value):
        return to_json_compatible(asdict(value))

    if isinstance(value, dict):
        return {str(key): to_json_compatible(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set | frozenset):
        return [to_json_compatible(item) for item in value]

    if isinstance(value, datetime | date | time):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Enum):
        return to_json_compatible(value.value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return to_json_compatible(model_dump(mode="json", exclude_none=True))
        except TypeError:
            return to_json_compatible(model_dump())

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_json_compatible(to_dict())

    if hasattr(value, "__dict__"):
        return to_json_compatible(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )

    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")
