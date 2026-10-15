"""Project pages surface sourced facts without promoting missing or historical data."""

from copy import deepcopy
from types import SimpleNamespace
import unittest

from datacenter_atlas import public_site


class ProjectPageContentTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "evidence_id": "e-status", "publisher": "Example operator",
            "title": "Facility update", "source_url": "https://example.org/update",
            "published_at": "2026-09-24", "kind": "company_disclosure",
        }
        self.context = SimpleNamespace(
            vocabulary=public_site.Vocabulary({}),
            atlas=SimpleNamespace(evidence_by_id={"e-status": self.source}),
            current=SimpleNamespace(kind="published", checkpoint_date="2026-10-15"),
            project_narratives={},
        )
        self.anchors = public_site._EvidenceAnchors(["e-status"])
        self.project = {
            "project_id": "p-one", "name": "Example campus",
            "last_observed_physical_status": "operational", "status_as_of": "2026-09-24",
            "status_method": "source_reported", "status_source": self.source,
            "status_age_days_at_review": 21,
            "operating_model": "unknown", "operating_model_unknown_reason": "Not established.",
            "development_type": "unknown", "workloads": [], "role_claims": [],
            "geometry_use_scope": "campus_locator", "geometry_evidence_id": "e-status",
            "independent_imagery_verification": False,
        }

    def test_missing_fields_do_not_fill_the_project_view(self):
        self.project.update({
            "power_unknown_reason": "No published project power observation.",
            "workload_unknown_reason": "No published workload statement.",
        })
        self.assertEqual(public_site._project_facts(self.context, self.project, self.anchors), [])
        rendered = public_site._project_section(self.context, self.project, self.anchors)
        for heading in ("Operating model", "Development type", "Companies", "Workloads"):
            self.assertNotIn(f"<dt>{heading}</dt>", rendered)
        self.assertNotIn("No evidence-linked role claims", rendered)
        self.assertNotIn("No published project power observation.", rendered)
        self.assertIn("2026-09-24", rendered)
        self.assertIn("Source and location review", rendered)
        self.assertIn("Campus Locator", rendered)
        self.assertIn("https://example.org/update", rendered)

    def test_known_facts_keep_scope_and_citations_without_mutating_data(self):
        self.project.update({
            "operating_model": "colocation", "operating_model_evidence_id": "e-status",
            "development_type": "greenfield",
            "role_claims": [{
                "party": "Example & Partner", "role": "operator",
                "relationship_scope": "project", "evidence_id": "e-status",
            }],
            "workloads": [{
                "workload": "ai", "deployment_scope": "planned",
                "method": "source_reported", "as_of_date": "2026-08-01",
                "evidence_id": "e-status",
            }],
        })
        original = deepcopy(self.project)
        facts = dict(public_site._project_facts(self.context, self.project, self.anchors))
        self.assertEqual(set(facts), {"Operating model", "Development type", "Companies", "Workloads"})
        self.assertIn("Example &amp; Partner", facts["Companies"])
        self.assertIn("(project)", facts["Companies"])
        self.assertIn("planned", facts["Workloads"])
        self.assertIn("2026-08-01", facts["Workloads"])
        self.assertIn('href="#evidence-e-status"', facts["Workloads"])
        self.assertEqual(self.project, original)

    def test_all_original_summaries_survive_a_new_status_narrative_once(self):
        records = [
            {
                "name": "Earlier plan", "summary": "The earlier plan covered two buildings.",
                "status": "announced", "status_as_of": "2025-05-01", "sources": [],
                "metrics": [{
                    "metric": "power_capacity", "value": 60, "unit": "MW", "qualifier": "up_to",
                    "basis": "planned", "applies_to": "campus", "as_of": "2025-05-01",
                    "note": "Campus total; not operational capacity.",
                }],
            },
            {
                "name": "Later phase", "summary": "The later phase added a third building.",
                "status": "under_construction", "status_as_of": "2026-01-10", "sources": [],
            },
        ]
        self.project["project_details"] = [{"record": record} for record in records]
        self.context.project_narratives = {
            "p-one": {"status": {"text": "The operator now reports the first building in service.",
                                  "evidence_id": "e-status"}}
        }
        original = deepcopy(self.project)
        rendered = (public_site._site_overview(self.context, [self.project], self.anchors)
                    + public_site._project_section(self.context, self.project, self.anchors))
        for record in records:
            self.assertEqual(rendered.count(record["summary"]), 1)
            self.assertIn(f'Source record as of {record["status_as_of"]}', rendered)
        self.assertEqual(rendered.count("The operator now reports the first building in service."), 1)
        self.assertIn("published 2026-09-24", rendered)
        self.assertIn("up to 60 MW", rendered)
        self.assertIn("Planned · Campus", rendered)
        self.assertIn("Campus total; not operational capacity.", rendered)
        self.assertEqual(self.project, original)

    def test_narrative_and_source_text_are_escaped_and_unsafe_urls_are_not_linked(self):
        self.source.update({"publisher": '<img src=x onerror="alert(1)">',
                            "source_url": "javascript:alert(1)"})
        rendered = public_site._narrative_html(
            self.context,
            {"text": '<script>alert("fact")</script> & a caveat.', "evidence_id": "e-status"},
            self.anchors,
        )
        self.assertIn("&lt;script&gt;alert(&quot;fact&quot;)&lt;/script&gt; &amp; a caveat.", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="#evidence-e-status"', rendered)

    def test_overview_without_saved_prose_still_gives_dated_sourced_status(self):
        rendered = public_site._site_overview(self.context, [self.project], self.anchors)
        self.assertIn("Example campus was reported operational", rendered)
        self.assertIn('<time datetime="2026-09-24">2026-09-24</time>', rendered)
        self.assertIn("Facility update", rendered)
        self.assertIn('href="#evidence-e-status"', rendered)
        self.assertNotIn("Unknown", rendered)

    def test_context_source_keeps_its_publication_date(self):
        self.context.project_narratives = {"p-one": {"context": [{
            "text": "The campus includes A and B buildings; the marker does not identify either plot.",
            "evidence_id": "e-status",
        }]}}
        rendered = public_site._project_section(self.context, self.project, self.anchors)
        self.assertIn("The campus includes A and B buildings", rendered)
        self.assertIn("the marker does not identify either plot.", rendered)
        self.assertIn("published 2026-09-24", rendered)
        self.assertLess(rendered.index("The campus includes A and B buildings"),
                        rendered.index("<details><summary>Source and location review"))

    def test_map_scope_warning_is_visible_for_imprecise_markers(self):
        cases = {
            "campus_locator": "individual project footprints are not mapped",
            "approximate_site_locator": "the exact facility position is unverified",
            "locality_context": "the facility position is not established",
            "host_estate_context": "the project&#x27;s position within it is not established",
        }
        for scope, warning in cases.items():
            with self.subTest(scope=scope):
                rendered = public_site._location_precision({"geometry_use_scopes": [scope]})
                self.assertIn(warning, rendered)
                self.assertNotIn("<details", rendered)


if __name__ == "__main__":
    unittest.main()
