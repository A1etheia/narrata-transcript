import dataclasses
import json
import unittest

from transcript.asr import (
    FEATURES,
    AudioInputError,
    BackendError,
    BackendIdentity,
    BackendInfo,
    BackendResult,
    BackendRuntimeError,
    BackendUnavailableError,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
    UnsupportedCapabilityError,
)

INFO = BackendInfo(backend_id="fake", model="fake-model")


class CapabilitiesTest(unittest.TestCase):
    def test_to_dict_is_json_ready_and_complete(self) -> None:
        capabilities = Capabilities(
            word_timestamps=True,
            devices=frozenset({"cuda", "cpu"}),
            max_audio_seconds=300,
        )

        data = json.loads(json.dumps(capabilities.to_dict()))

        self.assertEqual(set(data), {*FEATURES, "devices", "max_audio_seconds"})
        self.assertTrue(data["word_timestamps"])
        self.assertFalse(data["keyword_biasing"])
        self.assertEqual(data["devices"], ["cpu", "cuda"])
        self.assertEqual(data["max_audio_seconds"], 300)

    def test_features_are_exactly_the_boolean_fields(self) -> None:
        flags = [f.name for f in dataclasses.fields(Capabilities) if f.type is bool]

        self.assertEqual(list(FEATURES), flags)

    def test_invalid_values_are_rejected(self) -> None:
        for kwargs in (
            {"devices": frozenset()},
            {"devices": frozenset({"tpu"})},
            {"max_audio_seconds": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Capabilities(**kwargs)


class RequireTest(unittest.TestCase):
    def test_passes_for_a_declared_capability(self) -> None:
        Capabilities(word_confidence=True).require("word_confidence")

    def test_fails_only_for_a_missing_capability(self) -> None:
        with self.assertRaises(UnsupportedCapabilityError) as caught:
            Capabilities().require("speaker_labels")

        self.assertEqual(str(caught.exception), "capability missing: speaker_labels")
        self.assertFalse(caught.exception.retryable)

    def test_unknown_capability_is_a_programming_error(self) -> None:
        with self.assertRaises(ValueError):
            Capabilities().require("telepathy")


class ErrorsTest(unittest.TestCase):
    def test_retryable_per_category(self) -> None:
        expected = {
            AudioInputError: False,
            BackendUnavailableError: False,
            UnsupportedCapabilityError: False,
            ResourceError: True,
            BackendRuntimeError: True,
        }
        for error, retryable in expected.items():
            with self.subTest(error=error.__name__):
                self.assertTrue(issubclass(error, BackendError))
                self.assertIs(error("x").retryable, retryable)


class IdentityTest(unittest.TestCase):
    def test_matches_model_revision_and_settings_but_not_runtime(self) -> None:
        stored = dataclasses.replace(INFO, model_version="abc", runtime_version="1")
        identity = BackendIdentity(
            dataclasses.replace(stored, runtime_version="2"), {"beam_size": 5}
        )

        self.assertTrue(identity.matches(stored, {"beam_size": 5}))
        for info, settings in (
            (dataclasses.replace(stored, model_version="def"), {"beam_size": 5}),
            (dataclasses.replace(stored, model="other"), {"beam_size": 5}),
            (stored, {"beam_size": 4}),
        ):
            with self.subTest(info=info, settings=settings):
                self.assertFalse(identity.matches(info, settings))


class ResultTest(unittest.TestCase):
    def test_optional_fields_may_stay_empty(self) -> None:
        word = ResultWord(text="Drachenhort")
        segment = ResultSegment(text="Zum Drachenhort.", words=(word,))
        result = BackendResult(info=INFO, segments=(segment, ResultSegment(text="")))

        self.assertIsNone(word.confidence)
        self.assertIsNone(segment.start)
        self.assertIsNone(segment.speaker)
        self.assertEqual(result.keywords_used, ())
