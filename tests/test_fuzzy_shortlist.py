from __future__ import annotations

import unittest

from datacenter_atlas.fuzzy_shortlist import shortlist_priority


class FuzzyShortlistTests(unittest.TestCase):
    def test_explicit_markers_rank_ahead_of_text(self) -> None:
        self.assertEqual(
            shortlist_priority(
                {
                    "classification": "explicit_marker_variant",
                    "lifecycle_hint": "under_construction",
                    "trigger_tags": [{"key": "construction", "value": "data center"}],
                }
            ),
            (1, "explicit_lifecycle_marker"),
        )
        self.assertEqual(
            shortlist_priority(
                {
                    "classification": "unknown_key_explicit_value",
                    "lifecycle_hint": "lead",
                    "trigger_tags": [{"key": "building:part", "value": "data_center"}],
                }
            ),
            (3, "nonstandard_exact_marker"),
        )
        self.assertEqual(
            shortlist_priority(
                {
                    "classification": "textual_only",
                    "lifecycle_hint": "lead",
                    "trigger_tags": [{"key": "name", "value": "Example Data Center"}],
                }
            ),
            (4, "identity_text"),
        )

    def test_source_only_noise_is_not_shortlisted(self) -> None:
        self.assertIsNone(
            shortlist_priority(
                {
                    "classification": "textual_only",
                    "lifecycle_hint": "lead",
                    "trigger_tags": [
                        {
                            "key": "source",
                            "value": "China Data Center, University of Michigan",
                        }
                    ],
                }
            )
        )
        self.assertIsNone(
            shortlist_priority(
                {
                    "classification": "ambiguous",
                    "lifecycle_hint": "lead",
                    "trigger_tags": [{"key": "source:position", "value": "China Data Center"}],
                }
            )
        )

    def test_context_text_remains_low_priority_review(self) -> None:
        self.assertEqual(
            shortlist_priority(
                {
                    "classification": "textual_only",
                    "lifecycle_hint": "lead",
                    "trigger_tags": [{"key": "note", "value": "Near data center access"}],
                }
            ),
            (5, "context_text"),
        )


if __name__ == "__main__":
    unittest.main()
