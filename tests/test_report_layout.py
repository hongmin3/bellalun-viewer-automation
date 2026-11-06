import unittest
from core import report_layout as view


class ReportLayoutTests(unittest.TestCase):
    def test_null_is_distinct_from_empty_string(self):
        self.assertNotEqual(view.render_value(None), view.render_value(''))
        self.assertIn('None', view.render_value({'value': None}))
    def test_shell_is_offline_accessible_and_printable(self):
        text = view.render_shell(title='<QA>', product='제품', subtitle='시험',
                                 nav=[('overview', '요약')], body_html='<section id="overview">결론</section>')
        self.assertIn('&lt;QA&gt;', text)
        self.assertIn('lang="ko"', text)
        self.assertIn('beforeprint', text)
        self.assertNotIn('src="http', text)
        self.assertIn('report-layout-version', text)

    def test_structured_values_preserve_false_zero_and_escape(self):
        text = view.render_value({'count': 0, 'ready': False, 'value': '<script>x</script>'})
        self.assertIn('0', text)
        self.assertIn('False', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<script>', text)

    def test_long_note_is_folded_without_losing_original(self):
        note = '긴 원문' * 200
        text = view.render_note(note)
        self.assertIn('<details', text)
        self.assertIn(note, text)

    def test_step_preserves_unblock_and_not_verified(self):
        text = view.render_step(order=1, step=2, title='시험', status='BLOCKED',
                                expected=0, actual=False, unblock_condition='서버 연결', not_verified='되읽기')
        self.assertIn('서버 연결', text)
        self.assertIn('되읽기', text)
        self.assertIn('False', text)

    def test_detail_instance_keys_differ_for_repeated_tc(self):
        a = view.render_tc_detail(key='tc-1', tc_id='TC01', title='시험', status='PASS', body_html='내용')
        b = view.render_tc_detail(key='tc-2', tc_id='TC01', title='시험', status='FAIL', body_html='내용')
        self.assertIn('id="tc-1"', a)
        self.assertIn('id="tc-2"', b)
        self.assertNotIn(' open', a)
        self.assertIn(' open', b)


if __name__ == '__main__':
    unittest.main()
