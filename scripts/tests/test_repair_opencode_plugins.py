import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import uuid

spec=importlib.util.spec_from_file_location('repair_opencode_plugins',Path(__file__).resolve().parents[1]/'repair-opencode-plugins.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)


class RepairPluginTests(unittest.TestCase):
    def setUp(self):
        self.parent=Path(__file__).resolve().parents[2]/'.cache/native-acceptance-tests'
        self.parent.mkdir(parents=True,exist_ok=True)
        self.root=self.parent/('kairos-native-test-'+uuid.uuid4().hex);self.root.mkdir()
        self.root=self.root.resolve();self.addCleanup(self.cleanup)
        self.plugin=self.root/'plugins/custom-agents';self.plugin.mkdir(parents=True)
        (self.plugin/'package.json').write_text('{"name":"custom-agents-hooks"}',encoding='utf-8')
        (self.plugin/'index.js').write_text("export default { id: 'custom-agents', setup() {} };",encoding='utf-8')
        self.config=self.root/'opencode.json'
        self.original={'$schema':'https://opencode.ai/config.json','plugins':[self.plugin.as_posix(),'other-plugin'],
                       'model':'existing-model','mcp':{'foreign':{'enabled':True}},'synthetic_private_value':'NOT-A-REAL-SECRET'}
        self.config.write_text(json.dumps(self.original),encoding='utf-8')

    def cleanup(self):
        self.assertEqual(self.root.parent,self.parent.resolve())
        self.assertTrue(self.root.name.startswith('kairos-native-test-'))
        shutil.rmtree(self.root)

    def test_read_only_plan_detects_the_observed_double_registration(self):
        before=self.config.read_bytes();result=repair.repair(self.root)
        self.assertEqual(result['status'],'repair_required');self.assertEqual(result['redundant_entries'],1)
        self.assertEqual(self.config.read_bytes(),before);self.assertEqual(len(list(self.root.glob('*.bak'))),0)
        self.assertNotIn('NOT-A-REAL-SECRET',json.dumps(result))

    def test_apply_preserves_foreign_settings_code_and_original_backup_and_is_idempotent(self):
        before=self.config.read_bytes();source=(self.plugin/'index.js').read_bytes()
        result=repair.repair(self.root,True);desired=dict(self.original,plugins=['other-plugin'])
        self.assertEqual(json.loads(self.config.read_bytes()),desired)
        self.assertEqual((self.root/result['backup_file']).read_bytes(),before)
        self.assertEqual((self.plugin/'index.js').read_bytes(),source)
        self.assertEqual(repair.repair(self.root,True)['status'],'already_clean')
        self.assertEqual(len(list(self.root.glob('*.bak'))),1)

    def test_options_are_never_discarded(self):
        data=dict(self.original,plugins=[{'package':self.plugin.as_posix(),'options':{'required':True}}])
        self.config.write_text(json.dumps(data),encoding='utf-8');before=self.config.read_bytes()
        with self.assertRaises(repair.RepairError):repair.repair(self.root,True)
        self.assertEqual(self.config.read_bytes(),before)

    def test_failure_to_replace_leaves_original_and_recovery_backup(self):
        before=self.config.read_bytes()
        with patch.object(Path,'replace',side_effect=PermissionError):
            with self.assertRaises(PermissionError):repair.repair(self.root,True)
        self.assertEqual(self.config.read_bytes(),before)
        backups=list(self.root.glob('*.bak'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),before)
        self.assertEqual(list(self.root.glob('*.tmp')),[])

    def test_concurrent_change_is_not_overwritten(self):
        original_read=repair.read;count=0
        def changed(path):
            nonlocal count
            result=original_read(path)
            if Path(path)==self.config:
                count+=1
                if count==2:self.config.write_text('{"plugins":[],"foreign_change":true}',encoding='utf-8')
            return result
        with patch.object(repair,'read',side_effect=changed):
            with self.assertRaises(repair.RepairError):repair.repair(self.root,True)
        self.assertTrue(json.loads(self.config.read_bytes())['foreign_change'])

    def test_wrong_plugin_identity_is_rejected_before_writing(self):
        (self.plugin/'index.js').write_text("export default {id:'other'};",encoding='utf-8');before=self.config.read_bytes()
        with self.assertRaises(repair.RepairError):repair.repair(self.root,True)
        self.assertEqual(self.config.read_bytes(),before)


if __name__=='__main__':unittest.main()
