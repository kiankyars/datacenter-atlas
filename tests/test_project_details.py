"""Source scopes and citations stay readable without executing source text."""
import unittest

try:
    from datacenter_atlas.project_details import render_record, detail_sheets
except ImportError:
    from datacenter_atlas.datacenter_atlas.project_details import render_record, detail_sheets


class ProjectDetailTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            'id': 'example', 'summary': '<script>bad()</script>', 'status': 'announced', 'status_as_of': '2026-08-01',
            'status_source_ids': ['s1'], 'sources': [{'id': 's1', 'url': 'https://example.org/source', 'publisher': 'Example', 'title': 'Source'}],
            'metrics': [{'metric': 'power_capacity', 'value': 40, 'unit': 'MW', 'qualifier': 'up_to', 'basis': 'planned',
                         'applies_to': 'phase', 'phase_label': 'Phase one', 'as_of': '2026-08', 'source_ids': ['s1']}],
            'milestones': [{'event': 'fully_operational', 'date': '2029', 'kind': 'planned', 'source_ids': ['s1']}],
        }

    def test_scopes_qualifiers_and_partial_dates_survive(self):
        output = render_record(self.record)
        for value in ['up to 40 MW', 'Planned · Phase · Phase one', '2026-08', '2029', 'https://example.org/source']:
            self.assertIn(value, output)
        self.assertNotIn('2029-01-01', output)
        self.assertNotIn('<script>', output)
        self.assertIn('&lt;script&gt;', output)

    def test_unsafe_source_links_are_text(self):
        self.record['sources'][0]['url'] = 'javascript:alert(1)'
        self.assertNotIn('href="javascript:', render_record(self.record))

    def test_large_figures_and_decimal_ranges_are_readable(self):
        metric = self.record['metrics'][0]
        metric.update(value=50000000000, unit='USD')
        self.assertIn('50,000,000,000 USD', render_record(self.record))
        metric.update(value=1.25, value_high=2.75, unit='MW')
        self.assertIn('1.25–2.75 MW', render_record(self.record))

    def test_spreadsheet_metrics_remain_numbers_with_scope_and_citations(self):
        sheets = dict(detail_sheets([{'project_id': 'p1', 'project_details': [{'record': self.record}]}]))
        metrics = sheets['metrics']
        row = dict(zip(metrics[0], metrics[1]))
        self.assertEqual(row['value'], 40)
        self.assertEqual(row['qualifier'], 'up_to')
        self.assertEqual(row['phase_label'], 'Phase one')
        self.assertEqual(row['source_urls'], 'https://example.org/source')


if __name__ == '__main__':
    unittest.main()
