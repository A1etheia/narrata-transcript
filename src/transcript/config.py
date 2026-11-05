"""Base configuration: reads the YAML file and reports problems by file and key."""

import math
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from transcript.session import SessionKey, SessionPaths

_LANGUAGE_PATTERN = re.compile(r"[a-z]{2}")
_TOP_LEVEL_KEYS = {
    "language",
    "paths",
    "segmentation",
    "audio",
    "asr",
    "diarization",
    "narrata",
    "debug",
}
_PATHS_KEYS = {"root"}
_SEGMENTATION_KEYS = {"length_seconds", "overlap_seconds"}
_AUDIO_KEYS = {"sample_rate", "channels"}
_AUDIO_CHANNELS = (1, 2)
_ASR_KEYS = {"model", "device", "compute_type", "beam_size", "retries"}
_DIARIZATION_KEYS = {"model", "device", "retries"}
_NARRATA_KEYS = {"url", "groups"}
# The bearer token must not cross a network unencrypted; plain http is only for a
# Narrata on this machine.
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
_DEVICES = ("auto", "cpu", "cuda")  # for every model-backed step
MAX_RETRIES = 5  # per segment; the cap rules out endless retry loops


class ConfigError(Exception):
    """The configuration is missing or invalid; the message is meant for the user."""


@dataclass(frozen=True)
class Config:
    language: str
    root: Path
    debug: bool = False
    segment_length_seconds: float | None = None
    segment_overlap_seconds: float | None = None
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    asr_model: str = "large-v3-turbo"  # faster-whisper name or local model directory
    asr_device: str = "auto"  # one of _DEVICES; auto prefers cuda
    asr_compute_type: str | None = None  # None: float16 on cuda, int8 on cpu
    asr_beam_size: int = 5
    asr_retries: int = 2  # further attempts after a retryable failure
    # Hugging Face name or local model directory, loaded from the local cache only
    diarization_model: str = "pyannote/speaker-diarization-community-1"
    diarization_device: str = "auto"  # one of _DEVICES; auto prefers cuda
    diarization_retries: int = 2
    narrata_url: str | None = None  # base URL of the Narrata API host
    # Narrata group id per group slug; the endpoint addresses groups by id
    narrata_groups: dict[str, int] = field(default_factory=dict)

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
    if not _is_text(root):
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

    audio = _section(path, data, "audio", _AUDIO_KEYS)
    sample_rate = _positive_number(
        path, audio, "audio", "sample_rate", Config.audio_sample_rate, integer=True
    )
    channels = audio.get("channels", Config.audio_channels)
    if not _is_number(channels, int) or channels not in _AUDIO_CHANNELS:
        raise _invalid(path, "audio.channels", "must be 1 or 2")

    asr = _section(path, data, "asr", _ASR_KEYS)
    model = asr.get("model", Config.asr_model)
    if not _is_text(model):
        raise _invalid(path, "asr.model", "must be a model name or directory")
    device = _choice(path, asr, "asr", "device", Config.asr_device, _DEVICES)
    compute_type = asr.get("compute_type")
    if compute_type is not None and not _is_text(compute_type):
        raise _invalid(path, "asr.compute_type", "must be a name such as float16")
    beam_size = _positive_number(
        path, asr, "asr", "beam_size", Config.asr_beam_size, integer=True
    )
    retries = _retries(path, asr, "asr", Config.asr_retries)

    diarization = _section(path, data, "diarization", _DIARIZATION_KEYS)
    diarization_model = diarization.get("model", Config.diarization_model)
    if not _is_text(diarization_model):
        raise _invalid(path, "diarization.model", "must be a model name or directory")
    diarization_device = _choice(
        path, diarization, "diarization", "device", Config.diarization_device, _DEVICES
    )
    diarization_retries = _retries(
        path, diarization, "diarization", Config.diarization_retries
    )

    narrata = _section(path, data, "narrata", _NARRATA_KEYS)
    narrata_url = narrata.get("url")
    if narrata_url is not None and not _is_narrata_url(narrata_url):
        raise _invalid(
            path,
            "narrata.url",
            "must be an https URL without query, or http on localhost",
        )
    narrata_groups = _narrata_groups(path, narrata.get("groups"))

    return Config(
        language=language,
        root=Path(root),
        debug=debug,
        segment_length_seconds=length,
        segment_overlap_seconds=overlap,
        audio_sample_rate=sample_rate,
        audio_channels=channels,
        asr_model=model,
        asr_device=device,
        asr_compute_type=compute_type,
        asr_beam_size=beam_size,
        asr_retries=retries,
        diarization_model=diarization_model,
        diarization_device=diarization_device,
        diarization_retries=diarization_retries,
        narrata_url=narrata_url,
        narrata_groups=narrata_groups,
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
            "audio": {
                "sample_rate": config.audio_sample_rate,
                "channels": config.audio_channels,
            },
            "asr": {
                "model": config.asr_model,
                "device": config.asr_device,
                "compute_type": config.asr_compute_type,
                "beam_size": config.asr_beam_size,
                "retries": config.asr_retries,
            },
            "diarization": {
                "model": config.diarization_model,
                "device": config.diarization_device,
                "retries": config.diarization_retries,
            },
            "narrata": {
                "url": config.narrata_url,
                "groups": dict(config.narrata_groups),
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
    path: Path,
    section: dict[str, Any],
    section_name: str,
    key: str,
    default: Any = None,
    integer: bool = False,
) -> Any:
    value = section.get(key)
    if value is None:
        return default
    types = int if integer else (int, float)
    if not _is_number(value, types) or not 0 < value < math.inf:
        rule = (
            "must be a positive whole number"
            if integer
            else "must be a positive number"
        )
        raise _invalid(path, f"{section_name}.{key}", rule)
    return value


def _retries(
    path: Path, section: dict[str, Any], section_name: str, default: int
) -> int:
    value = section.get("retries")
    if value is None:
        return default
    if not _is_number(value, int) or not 0 <= value <= MAX_RETRIES:
        raise _invalid(
            path,
            f"{section_name}.retries",
            f"must be a whole number from 0 to {MAX_RETRIES}",
        )
    return value


def _choice(
    path: Path,
    section: dict[str, Any],
    section_name: str,
    key: str,
    default: str,
    options: tuple[str, ...],
) -> str:
    value = section.get(key, default)
    if value not in options:
        raise _invalid(
            path, f"{section_name}.{key}", f"must be one of {', '.join(options)}"
        )
    return value


def _is_narrata_url(value: Any) -> bool:
    if not _is_text(value):
        return False
    try:
        url = urllib.parse.urlsplit(value)
        host, _ = url.hostname, url.port  # .port raises on a malformed port
    except ValueError:
        return False
    if not host or url.username or url.password or url.query or url.fragment:
        return False
    return url.scheme == "https" or (url.scheme == "http" and host in _LOCAL_HOSTS)


def _narrata_groups(path: Path, value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _invalid(path, "narrata.groups", "must map group slugs to group ids")
    groups = {}
    for slug, group_id in value.items():
        try:
            SessionKey(slug, 1)  # validates the slug as a session key does
        except (TypeError, ValueError):
            raise _invalid(
                path, "narrata.groups", f"{slug!r} is not a group slug"
            ) from None
        if not _is_number(group_id, int) or group_id < 1:
            raise _invalid(
                path, f"narrata.groups.{slug}", "must be a positive whole number"
            )
        groups[slug] = group_id
    return groups


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_number(value: Any, types: type | tuple[type, ...]) -> bool:
    """YAML `true` is an int in Python; a number here never means a bool."""
    return isinstance(value, types) and not isinstance(value, bool)


def _missing(path: Path, key: str) -> ConfigError:
    return ConfigError(f"{path}: missing required key: {key}")


def _invalid(path: Path, key: str, rule: str) -> ConfigError:
    return ConfigError(f"{path}: invalid value for {key}: {rule}")
