"""Base configuration: reads the YAML file and reports problems by file and key."""

import dataclasses
import math
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal, get_args

import yaml

from transcript.narrata import ENTRY_TYPES
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
    "knowledge",
    "review",
    "render",
    "playback",
    "debug",
}
_PATHS_KEYS = {"root"}
_SEGMENTATION_KEYS = {"length_seconds", "overlap_seconds"}
_AUDIO_KEYS = {"sample_rate", "channels"}
_AUDIO_CHANNELS = (1, 2)
_ASR_KEYS = {"model", "device", "compute_type", "beam_size", "retries"}
_DIARIZATION_KEYS = {"model", "device", "retries"}
_NARRATA_KEYS = {"url", "groups", "recent_sessions", "archive_limit"}
# Bounds of the transcription-context query parameters, see ios-archiv
# docs/transcripts.md: `n` (recent_sessions) and `archive_limit`.
_RECENT_SESSIONS_RANGE = (1, 20)
_ARCHIVE_LIMIT_RANGE = (0, 2000)
_KNOWLEDGE_KEYS = {"keyword_budget"}
# Most glossary entries per type that become ASR keyword candidates; player
# characters are always candidates and do not count (TOOL-41).
DEFAULT_KEYWORD_BUDGET: dict[str, int] = {
    "person": 15,
    "place": 10,
    "organisation": 5,
    "artifact": 5,
    "event": 3,
    "lore": 3,
}
# The bearer token must not cross a network unencrypted; plain http is only for a
# Narrata on this machine.
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
_DEVICES = ("auto", "cpu", "cuda")  # for every model-backed step
MAX_RETRIES = 5  # per segment; the cap rules out endless retry loops

# The tiers of the Narrata contract's `confidence_tier`, from safe to unsafe.
Level = Literal["confident", "needs_review", "uncertain"]
LEVELS: tuple[Level, ...] = get_args(Level)

_RENDER_KEYS = {"timestamps"}
# Where a rendered transcript shows a time (TOOL-51): at each change of speaker,
# or at each passage.
TimestampRule = Literal["turn", "passage"]
TIMESTAMP_RULES: tuple[TimestampRule, ...] = get_args(TimestampRule)

_PLAYBACK_KEYS = {"filter"}
# A filter chain for speaker samples that was tried on the pilot (TOOL-91): a
# high-pass against footfall and hum, then FFT denoising. Off by default, since the
# raw samples sounded best there; playback only, nothing else reads it.
SUGGESTED_PLAYBACK_FILTER = "highpass=f=80,afftdn=nf=-25"


class ConfigError(Exception):
    """The configuration is missing or invalid; the message is meant for the user."""


@dataclass(frozen=True)
class SimilarThresholds:
    """When a recognised span counts as `similar` to a glossary term (TOOL-44)."""

    min_ratio: float = 0.85  # difflib ratio of the spellings
    min_length: int = 4  # letters a term and a span need
    max_length_deviation: float = 0.3  # of the term's length


@dataclass(frozen=True)
class UncertaintyThresholds:
    """The rules that rate a passage (TOOL-35); start values until calibrated."""

    word_low: float = 0.5  # a word below counts as low confidence
    word_very_low: float = 0.2  # one word below makes the passage needs_review
    low_share_review: float = 0.2  # share of low words for needs_review
    low_share_uncertain: float = 0.5  # share of low words for uncertain
    no_speech_prob: float = 0.6  # at or above: likely not speech
    avg_logprob: float = -1.0  # at or below: the decoder was unsure
    compression_ratio: float = 2.4  # at or above: repetitive output
    gap_ms: int = 2500  # longest silence between two words of a passage
    min_words_per_second: float = 1.0  # sparser speech may hide omitted words
    crosstalk_ms: int = 1000  # shorter crosstalk in a passage is table noise
    similar_level: Level = "needs_review"  # what a `similar` hint raises to
    # the same for a `similar` hint found by sound alone; most are false alarms
    similar_sound_level: Level = "confident"

    # (lower, upper): the first may not exceed the second
    ORDERED: ClassVar[tuple[tuple[str, str], ...]] = (
        ("word_very_low", "word_low"),
        ("low_share_review", "low_share_uncertain"),
    )

    def __post_init__(self) -> None:
        for low, high in self.ORDERED:
            if getattr(self, low) > getattr(self, high):
                raise ValueError(f"{low} must not exceed {high}")


# Per threshold: a choice of values, or a whole number or number within
# inclusive bounds.
_Spec = tuple[str, Any, Any]
_SIMILAR_SPEC: dict[str, _Spec] = {
    "min_ratio": ("number", 0, 1),
    "min_length": ("whole", 1, 50),
    "max_length_deviation": ("number", 0, 0.9),
}
_UNCERTAINTY_SPEC: dict[str, _Spec] = {
    "word_low": ("number", 0, 1),
    "word_very_low": ("number", 0, 1),
    "low_share_review": ("number", 0, 1),
    "low_share_uncertain": ("number", 0, 1),
    "no_speech_prob": ("number", 0, 1),
    "avg_logprob": ("number", -10, 0),
    "compression_ratio": ("number", 1, 10),
    "gap_ms": ("whole", 100, 60000),
    "min_words_per_second": ("number", 0, 10),
    "crosstalk_ms": ("whole", 1, 60000),
    "similar_level": ("choice", LEVELS, None),
    "similar_sound_level": ("choice", LEVELS, None),
}
_REVIEW_KEYS = {"similar", "uncertainty"}


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
    narrata_recent_sessions: int = 3  # sessions in the window of the `recent` tier
    narrata_archive_limit: int = 500  # most entries of the `archive` tier
    keyword_budget: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_KEYWORD_BUDGET)
    )
    review_similar: SimilarThresholds = SimilarThresholds()
    review_uncertainty: UncertaintyThresholds = UncertaintyThresholds()
    render_timestamps: TimestampRule = "turn"
    playback_filter: str | None = None  # an ffmpeg filter chain; None plays the raw WAV

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
    recent_sessions = _bounded_int(
        path,
        narrata,
        "narrata",
        "recent_sessions",
        Config.narrata_recent_sessions,
        _RECENT_SESSIONS_RANGE,
    )
    archive_limit = _bounded_int(
        path,
        narrata,
        "narrata",
        "archive_limit",
        Config.narrata_archive_limit,
        _ARCHIVE_LIMIT_RANGE,
    )

    knowledge = _section(path, data, "knowledge", _KNOWLEDGE_KEYS)
    keyword_budget = _keyword_budget(path, knowledge.get("keyword_budget"))

    review = _section(path, data, "review", _REVIEW_KEYS)
    similar_values = _thresholds(path, review, "review.", "similar", _SIMILAR_SPEC)
    similar = SimilarThresholds(**similar_values)
    uncertainty_values = _thresholds(
        path, review, "review.", "uncertainty", _UNCERTAINTY_SPEC
    )
    merged = dataclasses.asdict(UncertaintyThresholds()) | uncertainty_values
    for low, high in UncertaintyThresholds.ORDERED:
        if merged[low] > merged[high]:
            raise _invalid(
                path,
                f"review.uncertainty.{low}",
                f"must not exceed review.uncertainty.{high}",
            )
    uncertainty = UncertaintyThresholds(**merged)

    render = _section(path, data, "render", _RENDER_KEYS)
    timestamps = _choice(
        path, render, "render", "timestamps", Config.render_timestamps, TIMESTAMP_RULES
    )

    playback = _section(path, data, "playback", _PLAYBACK_KEYS)
    playback_filter = playback.get("filter")
    if playback_filter is False:
        playback_filter = None
    elif playback_filter is not None and not _is_text(playback_filter):
        raise _invalid(
            path, "playback.filter", "must be an ffmpeg filter chain or false"
        )

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
        narrata_recent_sessions=recent_sessions,
        narrata_archive_limit=archive_limit,
        keyword_budget=keyword_budget,
        review_similar=similar,
        review_uncertainty=uncertainty,
        render_timestamps=timestamps,
        playback_filter=playback_filter,
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
                "recent_sessions": config.narrata_recent_sessions,
                "archive_limit": config.narrata_archive_limit,
            },
            "knowledge": {"keyword_budget": dict(config.keyword_budget)},
            "review": {
                "similar": dataclasses.asdict(config.review_similar),
                "uncertainty": dataclasses.asdict(config.review_uncertainty),
            },
            "render": {"timestamps": config.render_timestamps},
            "playback": {"filter": config.playback_filter or False},
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
    path: Path, data: dict[str, Any], key: str, allowed: set[str], prefix: str = ""
) -> dict[str, Any]:
    """The mapping under `key`; `prefix` names its parent in messages, e.g. `review.`."""
    name = prefix + key
    section = data.get(key)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise _invalid(path, name, "must be a mapping")
    _reject_unknown_keys(path, section, allowed, f"{name}.")
    return section


def _thresholds(
    path: Path, parent: dict[str, Any], prefix: str, key: str, spec: dict[str, _Spec]
) -> dict[str, Any]:
    """The values given under `key`, checked against `spec`; absent keys are left out."""
    section = _section(path, parent, key, set(spec), prefix)
    name = prefix + key
    values: dict[str, Any] = {}
    for item in sorted(k for k, v in section.items() if v is not None):
        kind, low, high = spec[item]
        if kind == "choice":
            values[item] = _choice(path, section, name, item, "", low)
        elif kind == "whole":
            values[item] = _bounded_int(path, section, name, item, 0, (low, high))
        else:
            values[item] = _bounded_number(path, section, name, item, (low, high))
    return values


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
    return _bounded_int(
        path, section, section_name, "retries", default, (0, MAX_RETRIES)
    )


def _bounded_int(
    path: Path,
    section: dict[str, Any],
    section_name: str,
    key: str,
    default: int,
    bounds: tuple[int, int],
) -> int:
    value = section.get(key)
    if value is None:
        return default
    low, high = bounds
    if not _is_number(value, int) or not low <= value <= high:
        raise _invalid(
            path,
            f"{section_name}.{key}",
            f"must be a whole number from {low} to {high}",
        )
    return value


def _bounded_number(
    path: Path,
    section: dict[str, Any],
    section_name: str,
    key: str,
    bounds: tuple[float, float],
) -> float:
    """A present number within inclusive `bounds`, as a float."""
    value = section[key]
    low, high = bounds
    if not _is_number(value, (int, float)) or not low <= value <= high:
        raise _invalid(
            path, f"{section_name}.{key}", f"must be a number from {low} to {high}"
        )
    return float(value)


def _keyword_budget(path: Path, value: Any) -> dict[str, int]:
    """The budget per entry type; a type left out keeps its default."""
    if value is None:
        return dict(DEFAULT_KEYWORD_BUDGET)
    key = "knowledge.keyword_budget"
    if not isinstance(value, dict):
        raise _invalid(path, key, "must map entry types to whole numbers")
    _reject_unknown_keys(path, value, set(ENTRY_TYPES), f"{key}.")
    budget = dict(DEFAULT_KEYWORD_BUDGET)
    for entry_type, limit in value.items():
        if not _is_number(limit, int) or limit < 0:
            raise _invalid(
                path, f"{key}.{entry_type}", "must be a whole number from 0 up"
            )
        budget[entry_type] = limit
    return budget


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
