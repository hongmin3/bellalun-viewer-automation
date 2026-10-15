"""TC9/10 evidence contracts. These tests never touch USB, Viewer, files or DB.

The engine integration cases deliberately remain RED until the parent changes
tests/winupdate.py after the currently running source regression finishes.
"""
from copy import deepcopy
import importlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.result import FAIL, MANUAL, PASS, SKIP, TCResult


def import_evidence():
    """Synthetic normalized observations; no production identifiers or paths."""
    before = {'patient_id': 'SYNTHETIC_USB', 'examined_count': 1,
              'studies': [{'key': 1, 'study_uid': 'study.old'}],
              'instances': [{'key': 11, 'study_key': 1, 'series_uid': 'series.old',
                             'image_uid': 'image.old', 'path': 'synthetic/old.img',
                             'exists': True, 'readable': True, 'size': 128,
                             'file_identity': {'study_uid': 'study.old', 'series_uid': 'series.old',
                                               'image_uid': 'image.old'}}]}
    after = deepcopy(before)
    after['studies'].append({'key': 2, 'study_uid': 'study.imported'})
    after['instances'].append({'key': 12, 'study_key': 2, 'series_uid': 'series.imported',
                               'image_uid': 'image.imported', 'path': 'synthetic/imported.img',
                               'exists': True, 'readable': True, 'size': 128,
                               'file_identity': {'study_uid': 'study.imported', 'series_uid': 'series.imported',
                                                 'image_uid': 'image.imported'}})
    return {'before': before, 'after': after,
            'export_inventory': [{'path': 'synthetic/export.img', 'exists': True,
                                  'readable': True, 'size': 128}],
            'completion': {'observed': True, 'signal': 'synthetic-observed-success'},
            'examined': {'patient_id': 'SYNTHETIC_USB', 'searched': True,
                         'study_uids': ['study.imported'], 'count': 2}}


class USBImportEvidenceTests(unittest.TestCase):
    def verify(self, evidence):
        module = Path(__file__).resolve().parents[1] / 'core/usb_verification.py'
        self.assertTrue(module.is_file(), 'pure USB evidence verifier is required')
        verifier = importlib.import_module('core.usb_verification').verify_import_evidence
        return verifier(**evidence)

    def test_completion_new_patient_scoped_uids_readable_file_and_research_can_pass(self):
        result = self.verify(import_evidence())
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['study_uids'], ['study.imported'])
        self.assertEqual(result['image_uids'], ['image.imported'])

    def test_click_existing_examined_row_and_dialog_close_do_not_prove_import(self):
        evidence = import_evidence()
        evidence['after'] = deepcopy(evidence['before'])
        evidence['completion'] = {'observed': False, 'signal': 'clicked-and-manually-closed'}
        evidence['examined']['study_uids'] = ['study.old']
        evidence['examined']['count'] = 1
        self.assertFalse(self.verify(evidence)['ok'])

    def test_missing_or_error_completion_never_passes_even_with_new_data(self):
        for completion in [None, {}, {'observed': False, 'signal': 'clicked'},
                           {'observed': True, 'signal': ''},
                           {'observed': True, 'signal': 'synthetic-success', 'error': 'synthetic failure'}]:
            with self.subTest(completion=completion):
                evidence = import_evidence()
                evidence['completion'] = completion
                self.assertFalse(self.verify(evidence)['ok'])

    def test_action_only_signals_cannot_be_promoted_to_completion_by_observed_flag(self):
        for signal in ('clicked', 'import-button-clicked', 'manually-closed', 'duplicate-popup-dismissed'):
            evidence = import_evidence()
            evidence['completion']['signal'] = signal
            with self.subTest(signal=signal):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_existing_records_do_not_pass_even_when_file_timestamp_changes(self):
        evidence = import_evidence()
        evidence['after'] = deepcopy(evidence['before'])
        evidence['after']['instances'][0]['mtime_ns'] = 999
        evidence['after']['instances'][0]['sha256'] = 'new-content'
        self.assertFalse(self.verify(evidence)['ok'])

    def test_unrelated_patient_delta_cannot_satisfy_target_import(self):
        for place in ('before', 'after', 'examined'):
            evidence = import_evidence()
            evidence[place]['patient_id'] = 'UNRELATED_SYNTHETIC'
            with self.subTest(place=place):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_new_study_without_linked_new_image_does_not_pass(self):
        evidence = import_evidence()
        evidence['after']['instances'] = deepcopy(evidence['before']['instances'])
        self.assertFalse(self.verify(evidence)['ok'])
        evidence = import_evidence()
        evidence['after']['instances'][-1]['study_key'] = 1
        self.assertFalse(self.verify(evidence)['ok'])

    def test_unrelated_patient_row_cannot_be_hidden_inside_target_snapshot(self):
        for target in ('studies', 'instances'):
            evidence = import_evidence()
            evidence['after'][target][-1]['patient_id'] = 'UNRELATED_SYNTHETIC'
            with self.subTest(target=target):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_partial_import_with_an_unreadable_new_image_does_not_pass(self):
        evidence = import_evidence()
        other = deepcopy(evidence['after']['instances'][-1])
        other.update(key=13, image_uid='image.unreadable', path='synthetic/unreadable.img', readable=False)
        other['file_identity']['image_uid'] = 'image.unreadable'
        evidence['after']['instances'].append(other)
        evidence['export_inventory'].append(
            {'path': 'synthetic/export2.img', 'exists': True, 'readable': True, 'size': 128})
        self.assertFalse(self.verify(evidence)['ok'])

    def test_all_three_uids_must_be_regenerated(self):
        for field, target in [('study_uid', 'studies'), ('series_uid', 'instances'), ('image_uid', 'instances')]:
            evidence = import_evidence()
            evidence['after'][target][-1][field] = evidence['before'][target][0][field]
            with self.subTest(field=field):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_new_instance_requires_existing_readable_nonempty_target_file(self):
        for field, value in [('exists', False), ('readable', False), ('size', 0), ('path', '')]:
            evidence = import_evidence()
            evidence['after']['instances'][-1][field] = value
            with self.subTest(field=field):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_new_instance_requires_actual_img_xml_identity_for_all_three_uids(self):
        for identity in (None, {}, {'study_uid': 'study.imported'},
                         {'study_uid': 'study.imported', 'series_uid': 'series.imported', 'image_uid': ''}):
            evidence = import_evidence()
            evidence['after']['instances'][-1]['file_identity'] = identity
            with self.subTest(identity=identity):
                self.assertFalse(self.verify(evidence)['ok'])
        evidence = import_evidence()
        evidence['after']['instances'][-1].pop('file_identity')
        self.assertFalse(self.verify(evidence)['ok'])

    def test_img_xml_identity_must_match_linked_study_and_instance_db_uids(self):
        for field in ('study_uid', 'series_uid', 'image_uid'):
            evidence = import_evidence()
            evidence['after']['instances'][-1]['file_identity'][field] = 'wrong.or.reused.uid'
            with self.subTest(field=field):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_img_xml_parse_error_cannot_pass_even_with_retained_identity_values(self):
        evidence = import_evidence()
        evidence['after']['instances'][-1]['file_identity_error'] = 'synthetic XML parse error'
        self.assertFalse(self.verify(evidence)['ok'])

    def test_no_examined_research_cannot_pass(self):
        for examined in [None, {}, {'patient_id': 'SYNTHETIC_USB', 'searched': False,
                                    'study_uids': ['study.imported'], 'count': 2},
                         {'patient_id': 'SYNTHETIC_USB', 'searched': True,
                          'study_uids': ['study.old'], 'count': 1}]:
            evidence = import_evidence()
            evidence['examined'] = examined
            with self.subTest(examined=examined):
                self.assertFalse(self.verify(evidence)['ok'])

    def test_examined_card_count_increase_without_new_study_uid_never_passes(self):
        evidence = import_evidence()
        evidence['examined']['study_uids'] = []
        self.assertFalse(self.verify(evidence)['ok'])
        evidence['examined']['study_uids'] = ['study.old']
        self.assertFalse(self.verify(evidence)['ok'])

    def test_duplicate_new_study_uids_across_distinct_keys_are_rejected(self):
        evidence = import_evidence()
        evidence['after']['studies'].append({'key': 3, 'study_uid': 'study.imported'})
        image = deepcopy(evidence['after']['instances'][-1])
        image.update(key=13, study_key=3, series_uid='series.other', image_uid='image.other')
        evidence['after']['instances'].append(image)
        self.assertFalse(self.verify(evidence)['ok'])

    def test_duplicate_new_instance_uids_across_distinct_keys_are_rejected(self):
        evidence = import_evidence()
        image = deepcopy(evidence['after']['instances'][-1])
        image['key'] = 13
        evidence['after']['instances'].append(image)
        self.assertFalse(self.verify(evidence)['ok'])

    def test_same_series_uid_cannot_belong_to_distinct_studies(self):
        evidence = import_evidence()
        evidence['after']['studies'].append({'key': 3, 'study_uid': 'study.other'})
        image = deepcopy(evidence['after']['instances'][-1])
        image.update(key=13, study_key=3, image_uid='image.other')
        evidence['after']['instances'].append(image)
        evidence['examined']['study_uids'].append('study.other')
        self.assertFalse(self.verify(evidence)['ok'])

    def test_tuple_snapshots_are_normalized_without_mutation_or_type_error(self):
        for snapshot, field in [('before', 'studies'), ('after', 'studies'),
                                ('before', 'instances'), ('after', 'instances')]:
            evidence = import_evidence()
            evidence[snapshot][field] = tuple(evidence[snapshot][field])
            original = deepcopy(evidence)
            with self.subTest(snapshot=snapshot, field=field):
                result = self.verify(evidence)
                self.assertTrue(result['ok'], result)
                self.assertIsInstance(result['study_keys'], list)
                self.assertIsInstance(result['image_keys'], list)
                self.assertEqual(evidence, original)

    def test_evidence_is_not_mutated(self):
        evidence = import_evidence()
        original = deepcopy(evidence)
        self.verify(evidence)
        self.assertEqual(evidence, original)


class WindowsUpdateUSBSafetyTests(unittest.TestCase):
    def setUp(self):
        from tests import winupdate
        self.wu = winupdate
        self.stop_patch = patch.object(TCResult, 'stop_on_fail', False)
        self.stop_patch.start()
        self.addCleanup(self.stop_patch.stop)
        self.lookup = {'TC_Basic_WorkFlow_09': {'tc_id': 'TC_Basic_WorkFlow_09', 'verdict': PASS,
            'checks': [{'step': 1, 'title': 'synthetic prerequisite', 'status': PASS}]}}

    def outcome(self, evidence=None):
        imp = {'rows': 1, 'row_selected': True, 'imported_clicked': True,
               'duplicate_popup': True, 'closed': True, 'error': None}
        if evidence is not None:
            imp['evidence'] = evidence
        return {'drive': 'SYNTHETIC_USB',
                'export': {'files': ['synthetic/export.img'],
                           'inventory': [{'path': 'synthetic/export.img', 'exists': True,
                                          'readable': True, 'size': 128}]}, 'import': imp}

    def import_check(self, outcome):
        result = self.wu._wu_09(self.lookup, outcome)
        return next(check for check in result.checks if check.title == 'USB Import 되읽기')

    def test_current_click_only_import_remains_manual(self):
        self.assertEqual(self.import_check(self.outcome()).status, MANUAL)

    def test_unavailable_usb_remains_skip(self):
        result = self.wu._wu_09(self.lookup, {'drive': None})
        check = next(check for check in result.checks if check.title == 'USB Export/Import')
        self.assertEqual(check.status, SKIP)

    def test_import_error_and_outer_exception_remain_fail(self):
        outcome = self.outcome()
        outcome['import']['error'] = 'synthetic import error'
        self.assertEqual(self.import_check(outcome).status, FAIL)
        outcome = self.outcome()
        outcome['error'] = 'synthetic outer exception'
        result = self.wu._wu_09(self.lookup, outcome)
        self.assertEqual(result.checks[-1].status, FAIL)

    def test_exception_without_resolved_drive_is_failure_not_usb_absence(self):
        result = self.wu._wu_09(self.lookup, {'drive': None, 'error': 'synthetic failure'})
        check = next(check for check in result.checks if check.title == 'USB Export/Import')
        self.assertEqual(check.status, FAIL)

    def test_full_independent_import_evidence_will_be_pass_after_engine_integration(self):
        self.assertEqual(self.import_check(self.outcome(import_evidence())).status, PASS)

    def test_three_exported_images_with_three_verified_imported_images_can_pass(self):
        evidence = import_evidence()
        for key, suffix in [(13, 'second'), (14, 'third')]:
            image = deepcopy(evidence['after']['instances'][-1])
            image.update(key=key, image_uid=f'image.{suffix}', path=f'synthetic/{suffix}.img')
            image['file_identity']['image_uid'] = f'image.{suffix}'
            evidence['after']['instances'].append(image)
            evidence['export_inventory'].append(
                {'path': f'synthetic/export-{suffix}.img', 'exists': True, 'readable': True, 'size': 128})
        outcome = self.outcome(evidence)
        outcome['export']['inventory'] = deepcopy(evidence['export_inventory'])
        outcome['export']['files'] = [item['path'] for item in outcome['export']['inventory']]
        self.assertEqual(self.import_check(outcome).status, PASS)

    def test_three_exported_images_with_only_one_imported_image_must_fail(self):
        outcome = self.outcome(import_evidence())
        outcome['export']['files'] = ['synthetic/export1.img', 'synthetic/export2.img', 'synthetic/export3.img']
        outcome['export']['inventory'] = [
            {'path': path, 'exists': True, 'readable': True, 'size': 128}
            for path in outcome['export']['files']]
        self.assertEqual(self.import_check(outcome).status, FAIL)

    def test_one_selected_study_cannot_pass_with_two_new_studies(self):
        evidence = import_evidence()
        evidence['after']['studies'].append({'key': 3, 'study_uid': 'study.unexpected'})
        image = deepcopy(evidence['after']['instances'][-1])
        image.update(key=13, study_key=3, series_uid='series.unexpected',
                     image_uid='image.unexpected', path='synthetic/unexpected.img',
                     file_identity={'study_uid': 'study.unexpected', 'series_uid': 'series.unexpected',
                                    'image_uid': 'image.unexpected'})
        evidence['after']['instances'].append(image)
        evidence['examined']['study_uids'].append('study.unexpected')
        outcome = self.outcome(evidence)
        outcome['export']['inventory'].append(
            {'path': 'synthetic/export2.img', 'exists': True, 'readable': True, 'size': 128})
        self.assertEqual(self.import_check(outcome).status, FAIL)

    def test_import_without_export_inventory_must_fail(self):
        outcome = self.outcome(import_evidence())
        del outcome['export']['inventory']
        self.assertEqual(self.import_check(outcome).status, FAIL)

    def test_unreadable_empty_or_duplicate_export_inventory_cannot_prove_import(self):
        valid = {'path': 'C:/synthetic/export.img', 'exists': True, 'readable': True, 'size': 128}
        invalid = [None, [], [None], [dict(valid, exists=False)], [dict(valid, readable=False)],
                   [dict(valid, size=0)], [dict(valid, size=True)], [dict(valid, path='')],
                   [dict(valid, path='C:/synthetic/export.txt')],
                   [valid, dict(valid, path='c:\\SYNTHETIC\\export.img')]]
        for inventory in invalid:
            outcome = self.outcome(import_evidence())
            outcome['export']['inventory'] = inventory
            with self.subTest(inventory=inventory):
                self.assertEqual(self.import_check(outcome).status, FAIL)

    def test_forged_ok_without_independent_evidence_does_not_pass(self):
        outcome = self.outcome()
        outcome['import']['verification'] = {'ok': True}
        self.assertNotEqual(self.import_check(outcome).status, PASS)

    def complete_sweep(self):
        from core import flows
        return {'pages': {f'{group}.{page}': {'synthetic': {'value': 'x'}}
                          for group in flows.SETTING_GROUPS for page in flows.setting_pages(group)},
                'missing': {}, 'viewer_died': False}

    def setting_result(self, sweep, quick_count=24):
        # Bound every UI entry point before calling the real verdict function.
        from core import flows, setting_changes, setting_values
        with patch.object(flows, 'ensure_patient_screen', return_value=True), \
             patch.object(flows, 'open_setting'), \
             patch.object(setting_values, 'read_all', return_value=sweep), \
             patch.object(self.wu, '_quick_tab_check', return_value=[{'ok': True}] * quick_count), \
             patch.object(setting_changes, 'close_setting'):
            return self.wu.run_setting_display(SimpleNamespace(cfg={}), object())

    def test_tc10_empty_sweep_must_fail_after_engine_integration(self):
        result = self.setting_result({'pages': {}, 'missing': {}, 'viewer_died': False})
        self.assertEqual(result.checks[0].status, FAIL)

    def test_tc10_partial_sweep_must_fail_after_engine_integration(self):
        result = self.setting_result({'pages': {'system.general': {'synthetic': {'value': 'x'}}},
                                      'missing': {}, 'viewer_died': False})
        self.assertEqual(result.checks[0].status, FAIL)

    def test_tc10_empty_page_values_must_fail_after_engine_integration(self):
        sweep = self.complete_sweep()
        sweep['pages']['system.general'] = {}
        result = self.setting_result(sweep)
        self.assertEqual(result.checks[0].status, FAIL)

    def test_tc10_partial_quick_tabs_must_fail_after_engine_integration(self):
        result = self.setting_result(self.complete_sweep(), quick_count=1)
        self.assertEqual(result.checks[1].status, FAIL)

    def test_tc10_all_pages_nonempty_and_complete_quick_tabs_can_pass(self):
        result = self.setting_result(self.complete_sweep())
        self.assertEqual([check.status for check in result.checks], [PASS, PASS])

    def test_tc10_viewer_death_must_remain_fail(self):
        result = self.setting_result({'pages': {}, 'missing': {}, 'viewer_died': True})
        self.assertEqual(result.checks[0].status, FAIL)

    def test_tc10_closes_settings_when_sweep_raises(self):
        from core import flows, setting_changes, setting_values
        with patch.object(flows, 'ensure_patient_screen', return_value=True), \
             patch.object(setting_values, 'read_all', side_effect=RuntimeError('synthetic failure')), \
             patch.object(setting_changes, 'close_setting') as close:
            result = self.wu.run_setting_display(SimpleNamespace(cfg={}), object())
        self.assertEqual(result.verdict, FAIL)
        close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
