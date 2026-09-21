-- Excerpt from the Chado relational schema, version 1.4.
-- Source: https://github.com/GMOD/Chado/blob/1.4/schemas/1.4/default_schema.sql
-- License: Artistic-2.0. Retrieved 2026-09-11.
-- Only the feature tables are reproduced here. The full schema is about 2.2 MB.
-- Chado is the relational ancestor the GFF3 and LinkML feature models descend from,
-- and it is the fourth artifact in the 2026-09-08 link list that prompted this corpus.
--
-- Note the shape: Chado separates the feature itself from its location, in featureloc,
-- and expresses parent and child through feature_relationship. Neither is a nested
-- structure. That is the same normalization a flat-table profile would require.

create table feature (
    feature_id bigserial not null,
    primary key (feature_id),
    dbxref_id bigint,
    foreign key (dbxref_id) references dbxref (dbxref_id) on delete set null INITIALLY DEFERRED,
    organism_id bigint not null,
    foreign key (organism_id) references organism (organism_id) on delete cascade INITIALLY DEFERRED,
    name varchar(255),
    uniquename text not null,
    residues text,
    seqlen bigint,
    md5checksum char(32),
    type_id bigint not null,
    foreign key (type_id) references cvterm (cvterm_id) on delete cascade INITIALLY DEFERRED,
    is_analysis boolean not null default 'false',
    is_obsolete boolean not null default 'false',
    timeaccessioned timestamp not null default current_timestamp,
    timelastmodified timestamp not null default current_timestamp,
    constraint feature_c1 unique (organism_id,uniquename,type_id)
);

create table featureloc (
    featureloc_id bigserial not null,
    primary key (featureloc_id),
    feature_id bigint not null,
    foreign key (feature_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    srcfeature_id bigint,
    foreign key (srcfeature_id) references feature (feature_id) on delete set null INITIALLY DEFERRED,
    fmin bigint,
    is_fmin_partial boolean not null default 'false',
    fmax bigint,
    is_fmax_partial boolean not null default 'false',
    strand smallint,
    phase int,
    residue_info text,
    locgroup int not null default 0,
    rank int not null default 0,
    constraint featureloc_c1 unique (feature_id,locgroup,rank),
    constraint featureloc_c2 check (fmin <= fmax)
);

create table feature_relationship (
    feature_relationship_id bigserial not null,
    primary key (feature_relationship_id),
    subject_id bigint not null,
    foreign key (subject_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    object_id bigint not null,
    foreign key (object_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    type_id bigint not null,
    foreign key (type_id) references cvterm (cvterm_id) on delete cascade INITIALLY DEFERRED,
    value text null,
    rank int not null default 0,
    constraint feature_relationship_c1 unique (subject_id,object_id,type_id,rank)
);

create table feature_cvterm (
    feature_cvterm_id bigserial not null,
    primary key (feature_cvterm_id),
    feature_id bigint not null,
    foreign key (feature_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    cvterm_id bigint not null,
    foreign key (cvterm_id) references cvterm (cvterm_id) on delete cascade INITIALLY DEFERRED,
    pub_id bigint not null,
    foreign key (pub_id) references pub (pub_id) on delete cascade INITIALLY DEFERRED,
    is_not boolean not null default false,
    rank int not null default 0,
    constraint feature_cvterm_c1 unique (feature_id,cvterm_id,pub_id,rank)
);

create table featureprop (
    featureprop_id bigserial not null,
    primary key (featureprop_id),
    feature_id bigint not null,
    foreign key (feature_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    type_id bigint not null,
    foreign key (type_id) references cvterm (cvterm_id) on delete cascade INITIALLY DEFERRED,
    value text null,
    rank int not null default 0,
    cvalue_id bigint,
    FOREIGN KEY (cvalue_id) REFERENCES cvterm (cvterm_id) ON DELETE SET NULL,
    constraint featureprop_c1 unique (feature_id,type_id,rank)
);

create table feature_dbxref (
    feature_dbxref_id bigserial not null,
    primary key (feature_dbxref_id),
    feature_id bigint not null,
    foreign key (feature_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    dbxref_id bigint not null,
    foreign key (dbxref_id) references dbxref (dbxref_id) on delete cascade INITIALLY DEFERRED,
    is_current boolean not null default 'true',
    constraint feature_dbxref_c1 unique (feature_id,dbxref_id)
);

create table feature_synonym (
    feature_synonym_id bigserial not null,
    primary key (feature_synonym_id),
    synonym_id bigint not null,
    foreign key (synonym_id) references synonym (synonym_id) on delete cascade INITIALLY DEFERRED,
    feature_id bigint not null,
    foreign key (feature_id) references feature (feature_id) on delete cascade INITIALLY DEFERRED,
    pub_id bigint not null,
    foreign key (pub_id) references pub (pub_id) on delete cascade INITIALLY DEFERRED,
    is_current boolean not null default 'false',
    is_internal boolean not null default 'false',
    constraint feature_synonym_c1 unique (synonym_id,feature_id,pub_id)
);
