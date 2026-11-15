"""Native runtime boundaries remain independent of any external graph engine."""
from contextlib import nullcontext
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from memory_platform.config import Settings
from memory_platform import initialize, providers
from memory_platform.store import Store
from memory_platform.worker import Worker


class NativeRuntimeTests(unittest.TestCase):
    def test_backup_initializer_rejects_link_before_changing_permissions(self):
        root = Mock()
        root.is_symlink.return_value = True
        with patch.object(initialize, 'Path', return_value=root), patch.object(initialize.os, 'chown', create=True) as chown:
            with self.assertRaises(RuntimeError):
                initialize.main()
        root.mkdir.assert_not_called()
        chown.assert_not_called()

    def test_backup_initializer_changes_only_mount_root(self):
        root = Mock()
        root.is_symlink.return_value = False
        root.is_junction.return_value = False
        root.resolve.return_value = root
        with patch.object(initialize, 'Path', return_value=root) as path, patch.object(initialize.os, 'chown', create=True) as chown:
            initialize.main()
        path.assert_called_once_with('/backups')
        root.mkdir.assert_called_once_with(exist_ok=True)
        root.chmod.assert_called_once_with(0o700)
        chown.assert_called_once_with(root, 10001, 10001)

    def test_new_project_ignores_retired_operator_destinations(self):
        store = Store('unused', {'fixture': {'retired-adapter': 'obsolete'}})
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = None
        store.transaction = lambda: nullcontext(connection)
        store._global_admin = Mock()
        store._audit = Mock()
        store.create_project({'id': 'actor'}, {'id': 'fixture', 'title': 'Fixture'})
        insertion = next(call for call in connection.execute.call_args_list
                         if call.args[0].startswith('INSERT INTO memory.projects'))
        self.assertEqual(insertion.args[1][-1], '{}')

    def test_default_worker_has_only_native_providers_and_preserves_models(self):
        settings = Settings('unused')
        worker = Worker(Mock(), settings)
        self.assertEqual(set(worker.providers), {'embed'})  # extraction is off by default (MEMORY_EXTRACT_ENABLED)
        self.assertEqual(set(Worker(Mock(), Settings('unused', extract_enabled=True, llm_model='fixture-model')).providers), {'extract', 'embed'})
        self.assertEqual(settings.llm_model, '')  # no default model: the operator names one when turning a model feature on
        self.assertEqual(settings.embedding_model, 'nomic-embed-text')
        self.assertEqual(settings.ollama_url, 'http://ollama:11434')
        classes = {name for name, value in vars(providers).items()
                   if isinstance(value, type) and value.__module__ == providers.__name__}
        self.assertEqual(classes, {'ProviderError', 'Ollama', 'Embeddings'})

    def test_retired_job_cannot_be_rescheduled_as_a_new_destination(self):
        store = Store('unused')
        connection = Mock()
        store._jobs(connection, 'project', 'item', 1, 'a'*64, 'document',
                    ['retired-adapter', 'extract', 'embed'], 'upsert')
        scheduled = {call.args[1][6] for call in connection.execute.call_args_list}
        self.assertEqual(scheduled, {'extract', 'embed'})

    def test_retired_pending_job_is_failed_without_provider_execution(self):
        store = Store('unused')
        connection = Mock()
        selected = iter([{'id': 'owned-retired-job', 'destination': 'retired-adapter'}, None])
        def execute(query, parameters=None):
            result = Mock()
            if query.startswith('SELECT * FROM memory.jobs'):
                result.fetchone.return_value = next(selected)
            return result
        connection.execute.side_effect = execute
        store.transaction = lambda: nullcontext(connection)
        self.assertIsNone(store.claim_job('fixture-worker'))
        sweeps = [call for call in connection.execute.call_args_list if 'attempts_exhausted' in call.args[0]]
        self.assertEqual(len(sweeps), 1)  # the one statement that fails every poisoned job (it only takes `extract`/`embed`, so this row is left to the retired-destination path)
        updates = [call for call in connection.execute.call_args_list if call.args[0].startswith('UPDATE memory.jobs') and 'attempts_exhausted' not in call.args[0]]
        self.assertEqual(len(updates), 1)
        self.assertIn('destination_retired', updates[0].args[0])
        self.assertEqual(updates[0].args[1], ('owned-retired-job',))

    def test_worker_image_is_built_from_the_native_api_layer(self):
        dockerfile = Path(__file__).resolve().parents[1]/'Dockerfile'
        text = dockerfile.read_text(encoding='utf-8')
        self.assertIn('FROM api AS worker', text)
        worker = text.split('FROM api AS worker', 1)[1].split('FROM ', 1)[0]
        self.assertIn('memory_platform.worker', worker)
        self.assertNotIn('pip install', worker)
