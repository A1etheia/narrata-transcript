"""Base configuration: reads the YAML file and reports problems by file and key."""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from transcript.session import SessionKey, SessionPaths

_LANGUAGE_PATTERN = re.compile(r"[a-z]{2}")
_TOP_LEVEL_KEYS = {"language", "paths", "segmentation", "debug"}
_PATHS_KEYS = {"root"}
_SEGMENTATION_KEYS = {"length_seconds", "overlap_seconds"}


class ConfigError(Exception):
    """The configuration is missing or invalid; the message is meant for the user."""


@dataclass(frozen=True)
class Config:
    language: str
    root: Path
    debug: bool = False
    segment_length_seconds: float | None = None
    segment_overlap_seconds: float | None = None

    def session_paths(self, key: SessionKey) -> SessionPaths:
        return SessionPaths(key, self.root)


def load_config(path: Path) -> Config:
    data = _read_mapping(path)
    _reject_unknown_keys(path, data, _TOP_LEVEL_KEYS, "")

    language = data.get("language")
    if language is None:
        raise _missing(path, "language")
    if not isinstance(language, str) or not _LANGUAGE_PATTERN.fullmatch(language):
        raise _invalid(path, "language", "must be a two-letter code such as de")

    paths = _section(path, data, "paths", _PATHS_KEYS)
    root = paths.get("root")
    if root is None:
        raise _missing(path, "paths.root")
    if not isinstance(root, str) or not root:
        raise _invalid(path, "paths.root", "must be a non-empty path")

    debug = data.get("debug", False)
    if not isinstance(debug, bool):
        raise _invalid(path, "debug", "must be true or false")

    segmentation = _section(path, data, "segmentation", _SEGMENTATION_KEYS)
    length = _positive_number(path, segmentation, "segmentation", "length_seconds")
    overlap = _positive_number(path, segmentation, "segmentation", "overlap_seconds")
    if length is not None and overlap is not None and overlap >= length:
        raise _invalid(
            path,
            "segmentation.overlap_seconds",
            "must be smaller than segmentation.length_seconds",
        )

    return Config(
        language=language,
        root=Path(root),
        debug=debug,
        segment_length_seconds=length,
        segment_overlap_seconds=overlap,
    )


def format_config(config: Config) -> str:
    """Render the configuration in the same layout `load_config` reads."""
    return yaml.safe_dump(
        {
            "language": config.language,
            "paths": {"root": str(config.root)},
            "segmentation": {
                "length_seconds": config.segment_length_seconds,
                "overlap_seconds": config.segment_overlap_seconds,
            },
            "debug": config.debug,
        },
        sort_keys=False,
    )


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"{path}: cannot read file ({error.strerror})") from error
    except UnicodeDecodeError as error:
        raise ConfigError(f"{path}: file is not valid UTF-8") from error

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: invalid YAML: {error}") from error

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _section(
    path: Path, data: dict[str, Any], key: str, allowed: set[str]
) -> dict[str, Any]:
    section = data.get(key)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise _invalid(path, key, "must be a mapping")
    _reject_unknown_keys(path, section, allowed, f"{key}.")
    return section


def _reject_unknown_keys(
    path: Path, data: dict[str, Any], allowed: set[str], prefix: str
) -> None:
    unknown = sorted(str(key) for key in data if key not in allowed)
    if unknown:
        names = ", ".join(prefix + key for key in unknown)
        raise ConfigError(f"{path}: unknown key: {names}")


def _positive_number(
    path: Path, section: dict[str, Any], section_name: str, key: str
) -> float | None:
    value = section.get(key)
    if value is None:
        return None
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not is_number or not 0 < value < math.inf:
        raise _invalid(path, f"{section_name}.{key}", "must be a positive number")
    return value


def _missing(path: Path, key: str) -> ConfigError:
    return ConfigError(f"{path}: missing required key: {key}")


def _invalid(path: Path, key: str, rule: str) -> ConfigError:
    return ConfigError(f"{path}: invalid value for {key}: {rule}")
