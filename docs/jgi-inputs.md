# JGI files that need a login

Some profiles are developed against files from the
[JGI Data Portal](https://data.jgi.doe.gov/). Searching the portal needs no login, but
downloading any file does: `https://files.jgi.doe.gov/filedownload/<file id>/<file name>`
returns HTTP 401 without one (checked 2026-09-24). This repository therefore does not fetch
these files in CI. It records exactly which files are used, and checks copies that a person
has downloaded.

[model/examples/jgi-inputs.yaml](../model/examples/jgi-inputs.yaml) is the list. Each record
gives the portal record ID, the files selected from it, and each file's portal ID, size and
md5 as reported by the portal's search API.

## Getting the files

1. Log in at <https://data.jgi.doe.gov/>. JGI moved to ORCID login with two-factor
   authentication on 2026-07-27, per the notice on the Phytozome home page (read 2026-09-25).
2. Print the download URLs with `just jgi-urls`, and open each one in the logged-in browser.
   The portal's own download dialog can also produce a `curl --cookie ...` command. That
   command carries your session cookie: run it yourself and never commit it.
3. A file whose `status_when_collected` is `PURGED` is on tape. Select it in the portal and
   request a restore; the portal emails when it is ready. A 38-file restore requested on
   2026-09-24 was ready the next morning. `RESTORED` and `BACKUP_COMPLETE` files are on disk.
4. Put each file under `local/jgi/<record_id>/`, with the portal's file name, for example
   `local/jgi/IMG_AP-1268149/Ga0423362_functional_annotation.gff`. Portal zip downloads nest
   files under other folder names; move them into this layout.
5. Run `just jgi-verify`. It reports each listed file as `OK`, `MISSING`, `SIZE` or `MD5`.
   Missing files are expected, since nobody needs every record; a size or md5 mismatch fails.

`just jgi-collect` refreshes each record's `name`, `data_utilization_status` and `files` from
the search API. It keeps every other field, which is written by hand, including the
`file_name_pattern` that selects each record's files. The portal can list the
same file twice under different IDs; identical duplicates are merged and kept as
`duplicate_file_ids`, and a name listed with two different contents is an error.

## Reuse terms

Nothing under `local/jgi/` is committed unless its terms allow redistribution. Two records,
`IMG_AP-1268149` and `IMG_AP-1121004`, are vendored unchanged under `corpus/sources/jgi-img/`
([#53](https://github.com/turbomam/feature-table-corpus/issues/53)); the others stay local. Checked
2026-09-25:

- Which policy applies depends on when the proposal was accepted, recorded per record as
  `proposal_acceptance_date` and `governing_policy`. The current
  [JGI Data Policy](https://jgi.doe.gov/data-policy-support/data-policy) covers only "user
  projects accepted FY22 and later". Earlier projects fall under the
  [Legacy Data Policy](https://jgi.doe.gov/sites/default/files/2025-01/Data%26Support_LegacyDataPolicy.pdf).
  An earlier version of this page applied the current policy to every record, which was wrong.
- All four IMG records were accepted before FY22 (2012-03-22 to 2016-09-09), so the legacy
  policy governs them. For proposals accepted before November 2018 it says unreserved data "are
  freely available for any subsequent use", and a May 2021 update required that data to be
  public without use restrictions by 2023-05-31. Publications using the data should include:
  "These sequence data were produced by the US Department of Energy Joint Genome Institute
  http://www.jgi.doe.gov/ in collaboration with the user community." For later proposals it
  adds that "the source must still be cited". This repository treats attribution as required:
  each vendored entry gives the acknowledgment and the record's dataset DOI. Neither policy
  names a license.
- Every record in the manifest has `data_utilization_status: Unrestricted` in the search API.
- The search API gives no `proposal_acceptance_date` for the three Phytozome records, so which
  JGI policy governs them is not determined. Their own `DataReleasePolicy.html` files ask for
  citation, as below.
- Each Phytozome genome has a `DataReleasePolicy.html`, listed in the manifest. The three read
  so far say only "This data set is public. Please cite the following publication", and the
  manifest's `citation` field copies that publication. Phytozome also asks users to cite
  Goodstein et al. 2012, Nucleic Acids Research 40(D1):D1178-D1186.
- Phytozome tags TAIR10 and Araport11 `EXT`, sequenced outside JGI. TAIR's
  [licensing page](https://phoenixbioinformatics.atlassian.net/wiki/spaces/COM/pages/42216420/TAIR+Licensing)
  makes its `Public_Data_Releases` folder CC BY 4.0, allows limited excerpts of other data, and
  requires permission to redistribute substantial subsets. Whether TAIR10 is in that folder is
  not yet confirmed, so Arabidopsis files are used only as excerpts until it is.
