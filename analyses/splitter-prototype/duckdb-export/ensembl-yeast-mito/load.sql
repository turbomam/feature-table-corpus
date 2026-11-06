COPY biosequence FROM 'analyses/splitter-prototype/duckdb-export/ensembl-yeast-mito/biosequence.csv' (FORMAT 'csv', allow_quoted_nulls false, quote '"', delimiter ',', header 1);
COPY feature_record FROM 'analyses/splitter-prototype/duckdb-export/ensembl-yeast-mito/feature_record.csv' (FORMAT 'csv', allow_quoted_nulls false, force_not_null 'record_id', quote '"', delimiter ',', header 1);
COPY header_record FROM 'analyses/splitter-prototype/duckdb-export/ensembl-yeast-mito/header_record.csv' (FORMAT 'csv', allow_quoted_nulls false, force_not_null 'record_id', quote '"', delimiter ',', header 1);
COPY source_artifact FROM 'analyses/splitter-prototype/duckdb-export/ensembl-yeast-mito/source_artifact.csv' (FORMAT 'csv', allow_quoted_nulls false, quote '"', delimiter ',', header 1);
