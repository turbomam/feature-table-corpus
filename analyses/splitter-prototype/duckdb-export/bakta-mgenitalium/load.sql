COPY biosequence FROM 'analyses/splitter-prototype/duckdb-export/bakta-mgenitalium/biosequence.csv' (FORMAT 'csv', allow_quoted_nulls false, quote '"', delimiter ',', header 1);
COPY feature_record FROM 'analyses/splitter-prototype/duckdb-export/bakta-mgenitalium/feature_record.csv' (FORMAT 'csv', allow_quoted_nulls false, force_not_null 'record_id', quote '"', delimiter ',', header 1);
COPY header_record FROM 'analyses/splitter-prototype/duckdb-export/bakta-mgenitalium/header_record.csv' (FORMAT 'csv', allow_quoted_nulls false, force_not_null 'record_id', quote '"', delimiter ',', header 1);
COPY source_artifact FROM 'analyses/splitter-prototype/duckdb-export/bakta-mgenitalium/source_artifact.csv' (FORMAT 'csv', allow_quoted_nulls false, quote '"', delimiter ',', header 1);
