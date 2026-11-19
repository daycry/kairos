"""The documentation of the abstention says what the code does (T-91, CA-29): defaults, the uncalibrated model, the calibration tool and the note for Iniciativa 7."""
import json
import re
import unittest
from pathlib import Path

from memory_platform.config import abstain_from_env

ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION = ROOT / 'docs/configuration.md'


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


class AbstentionDocsTests(unittest.TestCase):
    def test_configuration_lists_both_variables_with_the_defaults_of_the_code(self):
        manual = CONFIGURATION.read_text(encoding='utf-8')
        default, thresholds = abstain_from_env({})
        self.assertEqual((default, thresholds), (False, {}))
        self.assertRegex(manual, r'\| `MEMORY_ABSTAIN_DEFAULT` \| `off` \|')
        self.assertRegex(manual, r'\| `MEMORY_ABSTAIN_THRESHOLDS` \| vacío \(sin umbrales\) \|')

    def test_the_measured_calibration_is_in_the_manual_with_its_risk_and_matches_the_gate(self):
        manual = CONFIGURATION.read_text(encoding='utf-8')
        for text in ('`uncalibrated`', 'R-07', 'measure_abstention', 'kairos-calib-', '0,60', '`abstention.simulated`'):
            self.assertIn(text, manual)
        thresholds = json.loads((ROOT / 'server/memory_platform/tests/retrieval_eval/thresholds.json').read_text(encoding='utf-8'))['abstention']
        self.assertIn(str(thresholds['simulated']['threshold']).replace('.', ','), manual)  # the simulated threshold the manual names is the one of the gate
        self.assertEqual(thresholds['models'], {})  # uncalibrated: no model has a threshold, as the manual says

    def test_operations_explains_the_gate_metrics_and_how_to_calibrate_a_real_model(self):
        operations = read('docs/operations.md')
        for text in ('abstención correcta', 'falsa', 'measure_abstention', '`abstention_false`', 'nunca el Ollama del equipo'):
            self.assertIn(text, operations)

    def test_both_changelogs_say_it_is_off_by_default_uncalibrated_and_what_it_changes_for_custom_agents(self):
        for path, expected in (('CHANGELOG.md', ('off` by default', 'uncalibrated', 'changes what `custom-agents` sees', 'Iniciativa 7')),
                               ('CHANGELOG.es.md', ('`off` por defecto', 'uncalibrated', 'cambia lo que ve `custom-agents`', 'Iniciativa 7'))):
            text = read(path)
            bullet = re.search(r'(?m)^- \*\*(?:Optional abstention in search|Abstención opcional en la búsqueda)\.\*\*.*$', text)
            self.assertIsNotNone(bullet, path)
            for fragment in expected:
                self.assertIn(fragment, bullet.group(0), path + ': ' + fragment)


if __name__ == '__main__':
    unittest.main()
