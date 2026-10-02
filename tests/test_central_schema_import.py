"""The feature model must build when another schema imports it, as bridge-central-schema does.

https://github.com/ber-data/bridge-central-schema/pull/5 found two failures only once the model
was imported: a dotted prefix the generated Python can't name, and prefixes the importing schema
has to declare again. These tests run LinkML's Python generator, which bridge-central-schema's
`just test` runs, so the next such failure shows up here first.
"""
from pathlib import Path
import shutil
import tempfile
import unittest

from linkml.generators.pythongen import PythonGenerator
from linkml_runtime import SchemaView

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "model/schema"
MODULES = ("ber_feature_model.yaml", "attributes.yaml")


def meaning_prefixes():
    """Prefixes used by enum meanings anywhere in the model, which an importer must declare."""
    view = SchemaView(str(SCHEMA_DIR / "ber_feature_model.yaml"))
    return sorted({value.meaning.split(":", 1)[0]
                   for enum in view.all_enums().values()
                   for value in enum.permissible_values.values() if value.meaning})


def generated_python_runs(schema_path):
    code = PythonGenerator(str(schema_path)).serialize()
    exec(compile(code, str(schema_path), "exec"), {"__name__": "generated"})


def stub_root(directory, *, extra_prefixes=(), name_slot=False):
    """A minimal importing schema shaped like bridge-central-schema's root."""
    for module in MODULES:
        shutil.copy(SCHEMA_DIR / module, directory / module)
    view = SchemaView(str(SCHEMA_DIR / "ber_feature_model.yaml"))
    prefixes = {"linkml": "https://w3id.org/linkml/", "stub": "https://example.org/stub/"}
    prefixes.update({p: view.schema.prefixes[p].prefix_reference for p in extra_prefixes})
    slots = ["id", "name"] if name_slot else ["id"]
    lines = ["id: https://example.org/stub", "name: stub", "default_prefix: stub", "prefixes:"]
    lines += [f"  {p}: {uri}" for p, uri in prefixes.items()]
    lines += ["imports:", "  - linkml:types", "  - ber_feature_model", "classes:", "  NamedThing:",
              f"    slots: [{', '.join(slots)}]", "slots:", "  id:", "    identifier: true"]
    if name_slot:
        lines += ["  name:", "    description: The importer's own name slot."]
    path = directory / "root.yaml"
    path.write_text("\n".join(lines) + "\n")
    return path


class CentralSchemaImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prefixes_are_python_identifiers(self):
        # gen-python names each prefix as a Python variable; EDAM.DATA became EDAM_DATA but was
        # still referenced as EDAM.DATA (https://github.com/linkml/linkml/issues/3458).
        view = SchemaView(str(SCHEMA_DIR / "ber_feature_model.yaml"))
        for prefix in view.schema.prefixes:
            self.assertTrue(prefix.replace("-", "_").isidentifier(), prefix)

    def test_generated_python_imports_on_its_own(self):
        generated_python_runs(SCHEMA_DIR / "ber_feature_model.yaml")

    def test_importer_that_declares_the_meaning_prefixes_builds(self):
        # LinkML's Python generator leaves out prefixes that only an imported module declares
        # (https://github.com/linkml/linkml/issues/2632), so the importer must declare these.
        self.assertEqual(meaning_prefixes(), ["EDAM_DATA", "MIXS"])
        generated_python_runs(stub_root(self.dir, extra_prefixes=meaning_prefixes()))

    def test_importer_without_the_meaning_prefixes_fails(self):
        # The control for the test above: without them the generated Python can't import.
        with self.assertRaises(NameError):
            generated_python_runs(stub_root(self.dir))

    @unittest.expectedFailure
    def test_importer_with_its_own_name_slot_builds(self):
        # bridge-central-schema's root defines name, and so does this model, so the import
        # fails with "Conflicting URIs ... for item: name". PR 5 renames the copy's slot to
        # display_name with alias name; whether this model should do the same is undecided.
        generated_python_runs(stub_root(self.dir, extra_prefixes=meaning_prefixes(), name_slot=True))


if __name__ == "__main__":
    unittest.main()
