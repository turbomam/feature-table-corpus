"""A LinkML validator loader that reads one GFF3 file as one unvalidated Dataset.

It follows linkml.validator.loaders.Loader (linkml 1.11.1, linkml/validator/loaders/loader.py),
the same shape as LinkML's YamlLoader: the constructor takes the source path and
iter_instances() yields plain dicts for the validation plugins to judge.

The conversion is the gff3-contig/4.0.0 profile in scripts/convert_features.py (import_source),
run with check_dataset=False so the closed Dataset checks are left to LinkML's plugins.
Row-level refusals (Is_circular, illegal phase, bad escapes, cardinality and others) still
happen during conversion; they raise Gff3ConversionRefused. See docs/linkml-gff-validation.md.

From the command line, scripts/ must be importable, for example PYTHONPATH=scripts, and the
loader is named in a linkml-validate config file:

    data_sources:
      - linkml_gff3_loader.Gff3Loader:
          source: corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3
          reference_context: NC_001417.2
          metadata_profile: ncbi
"""
from pathlib import Path

import click
from linkml.validator.loaders import Loader

from convert_features import ConversionError, import_source

PROFILE = "gff3-contig/4.0.0"


class Gff3ConversionRefused(click.ClickException):
    """The conversion profile refused the file, so there is no Dataset to validate.

    A click.ClickException so that linkml-validate, a click command, prints the message and
    exits 1 instead of printing a traceback. code is the converter's machine-readable code,
    for example circular-location, and __cause__ is the original ConversionError.
    """

    def __init__(self, source, error):
        self.source = source
        self.code = error.code
        super().__init__(f"{source}: the {PROFILE} conversion refused this file [{error.code}]: {error}")


class Gff3Loader(Loader):
    """Yield one Dataset (contigs and features) per GFF3 file.

    One Dataset, not one SequenceFeature at a time, because the checks that need a whole
    file (parents, duplicate IDs, contig lengths, cycles) can only report results from
    ValidationPlugin.process, which sees one instance; post_process returns nothing.

    :param source: path to a GFF3 file
    :param reference_context: assembly or source-scoped reference context; the converter
        requires one explicitly and does not guess it
    :param metadata_profile: generic, prodigal or ncbi (see scripts/source_document.py);
        under ncbi, a ##sequence-region from 1 gives the contig's length_bp
    """

    def __init__(self, source, *, reference_context, metadata_profile="generic") -> None:
        super().__init__(source)
        self.reference_context = reference_context
        self.metadata_profile = metadata_profile

    def iter_instances(self):
        path = Path(self.source)
        try:
            bundle = import_source(path.read_bytes(), profile=PROFILE, reference_context=self.reference_context,
                                   metadata_profile=self.metadata_profile, source_uri=path.resolve().as_uri(),
                                   check_dataset=False)
        except ConversionError as error:
            raise Gff3ConversionRefused(self.source, error) from error
        yield bundle["dataset"]
