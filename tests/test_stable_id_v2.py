from __future__ import annotations

import unittest

from datacenter_atlas.repository import stable_id, stable_id_v2


class StableIdV2Tests(unittest.TestCase):
    def test_named_fields_remove_legacy_delimiter_ambiguity(self) -> None:
        self.assertEqual(
            stable_id("evidence", "source|record", "revision"),
            stable_id("evidence", "source", "record|revision"),
        )
        self.assertEqual(
            stable_id("evidence", "source|record", "revision"),
            "06584478-bc4c-5da1-b841-01c928cd0470",
        )

        combined_source = stable_id_v2(
            "evidence",
            identity_fields={"source": "source|record"},
            temporal_semantics="content_revision",
            content_revision="revision",
        )
        split_source = stable_id_v2(
            "evidence",
            identity_fields={"source": "source", "record": "record"},
            temporal_semantics="content_revision",
            content_revision="revision",
        )
        self.assertNotEqual(combined_source, split_source)

    def test_content_revision_is_order_independent_and_capture_time_free(self) -> None:
        first = stable_id_v2(
            "evidence",
            identity_fields={
                "source_family": "operator-report",
                "source_record": {"region": "Québec", "rows": [1, 2]},
            },
            temporal_semantics="content_revision",
            content_revision="sha256:0123",
        )
        reordered = stable_id_v2(
            "evidence",
            identity_fields={
                "source_record": {"rows": [1, 2], "region": "Que\u0301bec"},
                "source_family": "operator-report",
            },
            temporal_semantics="content_revision",
            content_revision="sha256:0123",
        )
        self.assertEqual(first, reordered)
        self.assertEqual(first, "41c34bf6-6b03-5197-9c22-039dce69335d")

        with self.assertRaisesRegex(ValueError, "captured_at is excluded"):
            stable_id_v2(
                "evidence",
                identity_fields={"source_record": "row-1"},
                temporal_semantics="content_revision",
                content_revision="sha256:0123",
                captured_at="2026-07-20T00:00:00Z",
            )

    def test_captured_observation_canonicalizes_equivalent_instants(self) -> None:
        utc = stable_id_v2(
            "snapshot",
            identity_fields={"entity_id": "facility-1"},
            temporal_semantics="captured_observation",
            content_revision="sha256:abcd",
            captured_at="2026-07-20T07:00:00Z",
        )
        offset = stable_id_v2(
            "snapshot",
            identity_fields={"entity_id": "facility-1"},
            temporal_semantics="captured_observation",
            content_revision="sha256:abcd",
            captured_at="2026-07-20T00:00:00-07:00",
        )
        later = stable_id_v2(
            "snapshot",
            identity_fields={"entity_id": "facility-1"},
            temporal_semantics="captured_observation",
            content_revision="sha256:abcd",
            captured_at="2026-07-20T07:00:01Z",
        )
        self.assertEqual(utc, offset)
        self.assertNotEqual(utc, later)

    def test_temporal_semantics_and_json_types_are_identity_bearing(self) -> None:
        content = stable_id_v2(
            "record",
            identity_fields={"source_record": 1},
            temporal_semantics="content_revision",
            content_revision="revision-1",
        )
        capture = stable_id_v2(
            "record",
            identity_fields={"source_record": 1},
            temporal_semantics="captured_observation",
            content_revision="revision-1",
            captured_at="2026-07-20T00:00:00Z",
        )
        string_key = stable_id_v2(
            "record",
            identity_fields={"source_record": "1"},
            temporal_semantics="content_revision",
            content_revision="revision-1",
        )
        self.assertNotEqual(content, capture)
        self.assertNotEqual(content, string_key)

    def test_invalid_or_ambiguous_inputs_fail_closed(self) -> None:
        cases = (
            {},
            {"value": 1.0},
            {"value": {1, 2}},
            {"value": (1, 2)},
            {"value": {1: "not-a-string-key"}},
        )
        for identity_fields in cases:
            with self.subTest(identity_fields=identity_fields):
                with self.assertRaises((TypeError, ValueError)):
                    stable_id_v2(
                        "record",
                        identity_fields=identity_fields,
                        temporal_semantics="content_revision",
                        content_revision="revision-1",
                    )

        with self.assertRaisesRegex(TypeError, "content_revision"):
            stable_id_v2(
                "record",
                identity_fields={"source_record": "row-1"},
                temporal_semantics="content_revision",
            )
        with self.assertRaisesRegex(ValueError, "content_revision must be"):
            stable_id_v2(
                "record",
                identity_fields={"source_record": "row-1"},
                temporal_semantics="content_revision",
                content_revision="",
            )
        with self.assertRaisesRegex(ValueError, "captured_at is required"):
            stable_id_v2(
                "record",
                identity_fields={"source_record": "row-1"},
                temporal_semantics="captured_observation",
                content_revision="revision-1",
            )
        with self.assertRaisesRegex(ValueError, "whole-second precision"):
            stable_id_v2(
                "record",
                identity_fields={"source_record": "row-1"},
                temporal_semantics="captured_observation",
                content_revision="revision-1",
                captured_at="2026-07-20T00:00:00.1Z",
            )


if __name__ == "__main__":
    unittest.main()
