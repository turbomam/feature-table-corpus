#!/usr/bin/env python3
"""Run recommended LinkML lint with exact, listed naming exceptions."""
import argparse

from linkml.linter.linter import Linter, get_named_config


ALLOWED = {
    ("ber-feature-model", "standard_naming", "warning",
     f"Permissible value of Enum 'StrandEnum' has name '{symbol}'")
    for symbol in ("+", "-", ".", "?")
}
# The linter's canonical prefix is EDAM.DATA, but LinkML's Python generator can't name a
# prefix with a dot (https://github.com/linkml/linkml/issues/3458), so an importing schema that
# runs gen-python, as bridge-central-schema does, fails. Same conflict as
# https://github.com/linkml/linkml/issues/1512 for EDAM.TOPIC.
ALLOWED.add(("ber-feature-model", "canonical_prefixes", "warning",
             "Schema maps prefix 'EDAM_DATA' to namespace 'http://edamontology.org/data_' "
             "instead of using prefix 'EDAM.DATA'"))

# A dialect schema spells keys and values exactly as its source file does, so
# its naming exceptions are the source's own spellings, listed one by one.
DIALECT_NAMES = {
    "img_functional_gff": {
        "slots": ("ID", "Parent", "ncRNA_class"),
        "values": {
            "ImgFeatureType": ("CDS", "tRNA", "rRNA", "ncRNA", "tmRNA", "CRISPR"),
            "Strand": ("+", "-", "."),
            "StartType": ("ATG", "GTG", "TTG", "Edge"),
            "Partial": ("5'", "3'", "5',3'"),
            "SearchMode": ("Bacterial", "Archaeal"),
            "CleavageSiteNetwork": ("SignalP-noTM", "SignalP-TM"),
        },
    },
    "img_per_method_gff": {
        "slots": ("ID", "Name"),
        "values": {
            "ImgPerMethodStrand": (".",),
        },
    },
    "img_tmhmm_signalp_gff": {
        "slots": ("ID", "D_score"),
        "values": {
            "ImgTopologyFeatureType": ("Inside", "Outside", "TMhelix"),
            "ImgTopologyStrand": (".",),
            "SignalpNetwork": ("SignalP-noTM", "SignalP-TM"),
            "SignalpOrganismType": ("gram-",),
        },
    },
    "img_assembled_gff": {
        "slots": ("ID", "Model", "RNA_Class_ID", "Name", "Type", "LowScore"),
        "values": {
            "ImgAssembledFeatureType": ("CDS", "tRNA", "rRNA", "misc_RNA"),
            "ImgAssembledStrand": ("1", "-1"),
        },
    },
    "img_taxon_bundle": {
        "slots": ("ID", "EC"),
        "values": {
            "ImgTaxonFeatureType": ("CDS", "tRNA", "rRNA", "RNA", "CRISPR"),
            "Strand": ("+", "-"),
            "TmhmmFeatureType": ("TMhelix",),
            "DomainDatabase": ("SUPERFAMILY", "ProSiteProfiles", "ProSitePatterns", "SMART"),
            "XrefDatabase": ("GI", "GenBank/EMBL"),
        },
    },
    "phytozome_gene_exons_gff3": {
        "slots": ("ID", "Name", "Parent", "ancestorIdentifier"),
        "values": {
            "PhytozomeFeatureType": ("mRNA", "CDS", "five_prime_UTR", "three_prime_UTR"),
            "Strand": ("+", "-"),
        },
    },
    "phytozome_annotation_info": {
        "slots": ("pacId", "locusName", "transcriptName", "peptideName", "Pfam", "Panther", "KOG", "KO", "GO"),
        "values": {},
    },
}
for schema, names in DIALECT_NAMES.items():
    ALLOWED |= {(schema, "standard_naming", "warning", f"Slot has name '{name}'")
                for name in names["slots"]}
    ALLOWED |= {(schema, "standard_naming", "warning",
                 f"Permissible value of Enum '{enum}' has name '{value}'")
                for enum, values in names["values"].items() for value in values}


def allowed(problem):
    return (problem.schema_name, problem.rule_name, str(problem.level), problem.message) in ALLOWED


def lint(path):
    failures = []
    for problem in Linter(get_named_config("recommended")).lint(str(path)):
        if allowed(problem):
            continue
        failures.append(problem)
        print(f"{path}: {problem.level}: {problem.rule_name}: {problem.message}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schemas", nargs="+")
    args = parser.parse_args()
    failed = False
    for path in args.schemas:
        failed = bool(lint(path)) or failed
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
