CREATE TABLE biosequence(sequence_id VARCHAR, header_line_number BIGINT, header_text VARCHAR, residues VARCHAR, length BIGINT, "offset" BIGINT, line_bases INTEGER, line_bytes INTEGER, line_ending VARCHAR, last_line_ending VARCHAR, lines STRUCT(line_number BIGINT, bases INTEGER, line_ending VARCHAR, raw_text VARCHAR)[]);
CREATE TABLE feature_record(record_id VARCHAR PRIMARY KEY, line_number BIGINT, raw_text VARCHAR, kind VARCHAR, "scope" VARCHAR, sequence_id VARCHAR, metadata_type VARCHAR, metadata JSON, feature_columns VARCHAR[]);
CREATE TABLE header_record(record_id VARCHAR PRIMARY KEY, line_number BIGINT, raw_text VARCHAR, kind VARCHAR, "scope" VARCHAR, sequence_id VARCHAR, metadata_type VARCHAR, metadata JSON, feature_columns VARCHAR[]);
CREATE TABLE source_artifact(uri VARCHAR, sha256 VARCHAR, byte_size BIGINT);

