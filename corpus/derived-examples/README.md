# Selected real-source examples

These artifacts are generated from unchanged retained sources by explicit selection.
They are distinct from deliberately malformed and biologically altered fixtures.

`actinorhodin.gff3` is reproduced by `just bgc-report`; see the
[BGC exercise](../../analyses/bgc-query/README.md) for its scientific question,
selection rule, full source and limits on round-trip claims.

`populus-v4.1-chr01-200-genes.gene_exons.gff3` holds the first 200 genes on Chr01 of Populus
trichocarpa v4.1 (`Phytozome-533`), with all their mRNA, exon, CDS and UTR rows unchanged, the
source's three directives, and the three provenance lines. `scripts/populus_excerpt.py` writes it
from `Ptrichocarpa_533_v4.1.gene_exons.gff3.gz` (JGI file 5d94dc9fc0d65a87debccfce, md5
3fdcfdd5af213c5f4dde0c01f2cdbfda), which needs a JGI login and is too large to vendor, and checks
that md5 first. Phytozome lists this genome as public with citation required. Cite Tuskan et al.
2006, Science 313:1596 (doi:10.1126/science.1128691), and Goodstein et al. 2012, Nucleic Acids Res
40:D1178. JGI's legacy data policy asks for this acknowledgment: "These sequence data were
produced by the US Department of Energy Joint Genome Institute http://www.jgi.doe.gov/ in
collaboration with the user community."
