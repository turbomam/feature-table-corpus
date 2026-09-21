"""Real Pfam coordinates, explicit reference bindings, and two round-trip laws."""
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from convert_features import ConversionError, PROTEIN, import_source, export_source, reconstruct_record
from protein_context import build_context
from build_duckdb import build_database
from query_duckdb import interval_overlap, by_attribute, multiple_pfams

CONTEXT = ROOT / "model/examples/conversions/nmdc-pfam-context.json"
PFAM = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-5xxrm214.2_pfam.gff"
REFERENCE = "nmdc:wfmgas-11-19jh9v28.1"
GENE = REFERENCE + "_scf_10_c1_63_1091"


def imported(content, context):
    return import_source(content, profile=PROTEIN, reference_context=REFERENCE,
                         source_uri="urn:ftc:protein-test", protein_context=context)


class ProteinProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "local").mkdir(exist_ok=True)
        cls.context = json.loads(CONTEXT.read_text())
        cls.bundle = imported(PFAM.read_bytes(), cls.context)

    def test_real_context_reproduction_and_known_coordinates(self):
        entries = {e["id"]: e for e in yaml.safe_load((ROOT / "corpus/index.yaml").read_text())["entries"]}
        p, s, f = (entries["nmdc-biosample-" + name] for name in ("pfam", "structural", "proteins"))
        actual = build_context((ROOT / p["path"]).read_bytes(), (ROOT / s["path"]).read_bytes(),
                               (ROOT / f["path"]).read_bytes(), reference_context=REFERENCE,
                               annotation_uri=p["origin_url"], structural_uri=s["origin_url"], fasta_uri=f["origin_url"])
        self.assertEqual(actual, self.context)
        self.assertEqual(len(actual["bindings"]), 397)
        self.assertEqual(len(self.bundle["mappings"]), 416)
        features = self.bundle["dataset"]["features"]
        self.assertEqual(len(features), 813)
        parent = next(f for f in features if f["feature_id"] == GENE)
        self.assertEqual((parent["start"], parent["end"], parent["strand"]), (63, 1091, "-"))
        hits = [f for f in features if f.get("parent") == [GENE]]
        self.assertEqual(sorted((f["type"], f["start"], f["end"]) for f in hits),
                         [("PF13358", 168, 312), ("PF13518", 17, 70), ("PF13592", 95, 154)])
        self.assertTrue(all(f["coordinate_system"] == "protein" and f["seqid"] == parent["seqid"] for f in hits))

    def test_real_roundtrips_and_reconstruction_without_source_text(self):
        b = self.bundle
        self.assertEqual(export_source(b, mode="exact", original_bytes=PFAM.read_bytes(), protein_context=self.context), PFAM.read_bytes())
        canonical = export_source(b, mode="reconstruct", protein_context=self.context)
        again = imported(canonical, self.context)
        self.assertEqual(again["dataset"], b["dataset"])
        self.assertEqual(again["mappings"], b["mappings"])
        by_id = {f["feature_id"]: f for f in b["dataset"]["features"]}
        mapping = next(m for m in b["mappings"] if m["protein_id"] == GENE)
        columns = reconstruct_record(PROTEIN, by_id, mapping)
        self.assertEqual(columns[0], GENE)
        self.assertNotIn("Parent=", columns[8])
        self.assertNotEqual(columns[0], by_id[GENE]["seqid"])

    def test_context_is_required_unambiguous_and_bounded(self):
        bad = []
        bad.append(None)
        c = deepcopy(self.context); c["reference_context"] = "different:assembly"; bad.append(c)
        c = deepcopy(self.context); c["bindings"].append(c["bindings"][0]); bad.append(c)
        c = deepcopy(self.context); c["bindings"][0]["cds_id"] = "absent"; bad.append(c)
        c = deepcopy(self.context); c["dataset"]["features"][0]["translated_sequence"] = "M"; bad.append(c)
        c = deepcopy(self.context); c["dataset"]["features"][0]["type"] = "gene"; bad.append(c)
        c = deepcopy(self.context); c["context_version"] = True; bad.append(c)
        for context in bad:
            with self.subTest(context_type=type(context).__name__), self.assertRaises(ConversionError):
                imported(PFAM.read_bytes(), context)
        with self.assertRaises(ConversionError):
            import_source(PFAM.read_bytes(), profile="gff3-contig/1.0.0", reference_context=REFERENCE,
                          source_uri="urn:test", protein_context=self.context)

    def test_profile_refuses_incompatible_rows_and_edited_bundles(self):
        first = PFAM.read_bytes().splitlines()[0].decode().split("\t")
        c = deepcopy(self.context)
        parent = next(f for f in c["dataset"]["features"] if f["feature_id"] == first[0])
        c["dataset"] = {"contigs": [{"contig_id": parent["seqid"]}], "features": [parent]}
        c["bindings"] = [{"protein_id": first[0], "cds_id": first[0]}]
        self.assertEqual(len(imported(("\t".join(first) + "\n").encode(), c)["mappings"]), 1)
        for column, value, code in [(0, "unknown-protein", "protein-reference"), (2, "gene", "protein-profile"),
                                    (1, "Prodigal", "protein-profile"), (4, "999999", "protein-bound"),
                                    (6, "+", "protein-profile"), (7, "0", "phase-domain")]:
            cols = first.copy(); cols[column] = value
            with self.subTest(column=column), self.assertRaises(ConversionError) as caught:
                imported(("\t".join(cols) + "\n").encode(), c)
            self.assertEqual(caught.exception.code, code)
        for key, value in [("start", 999999), ("coordinate_system", "contig"), ("seqid", "wrong"), ("parent", ["wrong"])]:
            b = deepcopy(self.bundle); b["dataset"]["features"][-1][key] = value
            for mode in ("exact", "reconstruct"):
                with self.subTest(key=key, mode=mode), self.assertRaises(ConversionError):
                    export_source(b, mode=mode, protein_context=self.context)

    def test_generated_attributes_and_nontrivial_reference_mapping(self):
        rng = random.Random(25)
        parent = next(f for f in self.context["dataset"]["features"] if f["feature_id"] == GENE)
        c = deepcopy(self.context)
        c["dataset"] = {"contigs": [{"contig_id": parent["seqid"]}], "features": [parent]}
        c["bindings"] = [{"protein_id": "protein alias", "cds_id": GENE}]
        for _ in range(20):
            start = rng.randint(1, 200); end = rng.randint(start, 300)
            content = (f"# observed metadata\r\nprotein%20alias\tHMMER 3.1b2\tPF13358\t{start:05}\t{end}\t1e1\t.\t.\t"
                       "ID=hit;unknown=x%3By;unknown=;Note=a%2Cb,,c;\r\n").encode()
            b = imported(content, c)
            self.assertEqual(export_source(b, mode="exact", protein_context=c), content)
            again = imported(export_source(b, mode="reconstruct", protein_context=c), c)
            self.assertEqual(again["dataset"], b["dataset"])
            self.assertEqual(b["dataset"]["features"][-1]["parent"], [GENE])

    def test_queries_keep_protein_and_contig_spaces_separate(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            source = Path(directory) / "dataset.json"; db = Path(directory) / "example.duckdb"
            source.write_text(json.dumps(self.bundle["dataset"]))
            build_database(ROOT / "model/schema/ber_feature_model.yaml", source, db)
            with duckdb.connect(str(db), read_only=True) as con:
                self.assertEqual(len(interval_overlap(con, GENE, 17, 70, "protein")), 1)
                self.assertEqual(interval_overlap(con, GENE, 17, 70, "contig"), [])
                self.assertEqual(interval_overlap(con, REFERENCE + "_scf_10_c1", 17, 70, "protein"), [])
                self.assertEqual(len(interval_overlap(con, REFERENCE + "_scf_10_c1", 17, 70, "contig")), 1)
                self.assertTrue(by_attribute(con, "Name", "DDE_3"))
                self.assertEqual(by_attribute(con, "Name", "absent-domain"), [])
                self.assertTrue(any(GENE in row for row in multiple_pfams(con, ["PF13358", "PF13592", "PF13518"])))

    def test_cli_context_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            bundle = Path(directory) / "bundle.json"; restored = Path(directory) / "restored.gff"
            command = [sys.executable, str(ROOT / "scripts/convert_features.py"), "import", str(PFAM),
                       "--profile", PROTEIN, "--reference-context", REFERENCE, "--protein-context", str(CONTEXT),
                       "--output", str(bundle)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = bundle.read_bytes()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(before, bundle.read_bytes())
            result = subprocess.run([sys.executable, str(ROOT / "scripts/convert_features.py"), "export", str(bundle),
                                     "--mode", "exact", "--original", str(PFAM), "--protein-context", str(CONTEXT),
                                     "--output", str(restored)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(restored.read_bytes(), PFAM.read_bytes())

    def test_coordinated_context_edits_require_independent_original(self):
        for mutation in ("translation", "binding", "provenance"):
            changed = deepcopy(self.context)
            parent = changed["dataset"]["features"][0]
            if mutation == "translation":
                parent["translated_sequence"] = "V" + parent["translated_sequence"][1:]
            elif mutation == "binding":
                old = parent["feature_id"]
                parent["feature_id"] += ":changed"
                next(b for b in changed["bindings"] if b["cds_id"] == old)["cds_id"] = parent["feature_id"]
            else:
                changed["artifacts"][0]["sha256"] = "0" * 64
            # Reimport constructs a consistent bundle from the edited input.
            edited = imported(PFAM.read_bytes(), changed)
            for mode in ("exact", "reconstruct"):
                with self.subTest(mutation=mutation, mode=mode), self.assertRaises(ConversionError) as caught:
                    export_source(edited, mode=mode, original_bytes=PFAM.read_bytes(), protein_context=self.context)
                self.assertEqual(caught.exception.code, "protein-context-edited")
        for mode in ("exact", "reconstruct"):
            with self.assertRaises(ConversionError) as caught:
                export_source(self.bundle, mode=mode)
            self.assertEqual(caught.exception.code, "protein-context-original")

    def test_context_launcher_reproduces_json_and_preserves_failure_status(self):
        entries = {e["id"]: e for e in yaml.safe_load((ROOT / "corpus/index.yaml").read_text())["entries"]}
        p, s, f = (entries["nmdc-biosample-" + name] for name in ("pfam", "structural", "proteins"))
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            output = Path(directory) / "context with spaces.json"
            command = ["just", "protein-context", str(ROOT / p["path"]), str(ROOT / s["path"]),
                       str(ROOT / f["path"]), REFERENCE, str(output), "--annotation-uri", p["origin_url"],
                       "--structural-uri", s["origin_url"], "--fasta-uri", f["origin_url"]]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text()), self.context)
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), before)
            command[3] = str(Path(directory) / "missing structural.gff")
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
