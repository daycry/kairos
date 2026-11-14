"""MEMORY_EXTRACT_ENABLED (CA-14, P-03): with extraction off a `generate: true` event is accepted without an `extract` job."""
import copy
import os
import unittest

from memory_platform.config import Settings
from memory_platform.store import Store
from memory_platform.tests.test_store import create_core, event


def destinations(store, item_id):
    with store.transaction() as c:
        return sorted(row['destination'] for row in c.execute('SELECT destination FROM memory.jobs WHERE item_id=%s', (item_id,)).fetchall())


class ExtractSwitchTests(unittest.TestCase):
    def setUp(self):
        self.store, self.actor, self.pid = create_core()

    def enabled_store(self):
        store = Store(os.environ['MEMORY_TEST_DSN'], embedding_enabled=self.store.embedding_enabled)
        store.extraction_enabled = True
        return store

    def test_default_settings_have_extraction_off(self):
        self.assertIs(Settings('unused').extract_enabled, False)
        self.assertIs(getattr(Store('unused'), 'extraction_enabled', False), False)

    def test_summary_with_generate_is_accepted_without_extract_job(self):
        value = event(self.pid, event_type='summary')
        self.assertTrue(value['generate'])
        receipt = self.store.ingest_event(self.actor, value)
        self.assertEqual(receipt['status'], 'accepted')
        self.assertEqual(receipt['extraction'], 'disabled')
        self.assertNotIn('extract', destinations(self.store, value['item_id']))
        self.assertEqual(set(receipt) - {'extraction'}, {'event_id', 'item_id', 'version', 'status', 'jobs'})

    def test_embedding_job_is_unaffected_by_the_switch(self):
        store = Store(os.environ['MEMORY_TEST_DSN'], embedding_enabled=True)
        value = event(self.pid, event_type='summary')
        store.ingest_event(self.actor, value)
        self.assertEqual(destinations(store, value['item_id']), ['embed'])

    def test_replay_returns_the_same_receipt(self):
        value = event(self.pid, event_type='summary')
        first = self.store.ingest_event(self.actor, value)
        self.assertEqual(self.store.ingest_event(self.actor, copy.deepcopy(value)), first)

    def test_event_without_generate_has_no_extraction_field(self):
        receipt = self.store.ingest_event(self.actor, event(self.pid, generate=False))
        self.assertNotIn('extraction', receipt)

    def test_enabled_keeps_the_extract_job_and_no_field(self):
        store = self.enabled_store()
        value = event(self.pid, event_type='summary')
        receipt = store.ingest_event(self.actor, value)
        self.assertNotIn('extraction', receipt)
        self.assertIn('extract', destinations(store, value['item_id']))

    def test_delete_with_generate_does_not_claim_a_disabled_extraction(self):
        value = event(self.pid)
        self.store.ingest_event(self.actor, value)
        receipt = self.store.ingest_event(self.actor, dict(value, event_id=event(self.pid)['event_id'], version=2, event_type='delete'))
        self.assertNotIn('extraction', receipt)


if __name__ == '__main__':
    unittest.main()
