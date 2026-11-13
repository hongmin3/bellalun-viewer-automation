"""Validates: REQ-FOLLOWUP-001. 실행 신원과 저장점 재개 안전 경계."""
import json
from pathlib import Path
import tempfile
import unittest

from core.source_identity import combine_run_identity, execution_fingerprint
from core import wu_chain


class IdentityFollowupTests(unittest.TestCase):
    def test_unknown_dirty_never_becomes_known_dirty_or_clean(self):
        known = {'source_commit': 'a' * 40, 'source_dirty': False}
        unknown = {'source_commit': 'a' * 40, 'source_dirty': None}
        self.assertIsNone(combine_run_identity(unknown, known)['source_dirty'])
        self.assertIsNone(combine_run_identity(known, unknown)['source_dirty'])
        self.assertIsNone(combine_run_identity(unknown, unknown)['source_dirty'])

    def test_checkpoint_rejects_old_or_changed_execution_fingerprint(self):
        scratch = Path(__file__).resolve().parents[1] / 'work/followup-identity'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = str(Path(directory) / 'checkpoint.json')
            identity = wu_chain.chain_identity(['A'])
            old = wu_chain.Checkpoint(path, identity)
            old.save()
            with self.assertRaisesRegex(wu_chain.CheckpointError, '지문'):
                wu_chain.Checkpoint.load(path, identity, execution_fingerprint='approved')
            current = wu_chain.Checkpoint(path, identity, execution_fingerprint='approved')
            current.save()
            loaded = wu_chain.Checkpoint.load(path, identity, execution_fingerprint='approved')
            self.assertEqual(loaded.payload['execution_fingerprint'], 'approved')
            for changed in ('different-config', 'different-baseline', 'restored-generation'):
                with self.assertRaisesRegex(wu_chain.CheckpointError, '지문'):
                    wu_chain.Checkpoint.load(path, identity, execution_fingerprint=changed)
            self.assertEqual(json.loads(Path(path).read_text(encoding='utf-8'))['payload'],
                             current.payload)

    def test_restore_generation_must_match_to_reuse_real_checkpoint(self):
        scratch = Path(__file__).resolve().parents[1] / 'work/followup-identity'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = str(Path(directory) / 'checkpoint.json')
            fingerprint = execution_fingerprint('approved-plan', 'before-restore')
            checkpoint = wu_chain.Checkpoint(path, 'chain', execution_fingerprint=fingerprint)
            checkpoint.save()
            with self.assertRaises(wu_chain.CheckpointError):
                wu_chain.Checkpoint.load(path, 'chain', execution_fingerprint=
                                         execution_fingerprint('approved-plan', 'after-restore'))
            self.assertEqual(wu_chain.Checkpoint.load(path, 'chain', execution_fingerprint=
                             execution_fingerprint('approved-plan', 'before-restore')).payload,
                             checkpoint.payload)
