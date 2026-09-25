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

`just jgi-collect` refreshes the file lists from the search API. It keeps the hand-written
fields and the `file_name_pattern` that selects each record's files. The portal can list the
same file twice under different IDs; identical duplicates are merged and kept as
`duplicate_file_ids`, and a name listed with two different contents is an error.

## Reuse terms

Nothing under `local/jgi/` is committed unless its terms allow redistribution. Checked
2026-09-25:

- The [JGI Data Policy](https://jgi.doe.gov/data-policy-support/data-policy) says that after
  the embargo period, data "are unrestricted for use". Asking the proposal PI before
  redistributing applies only to use-restricted data. The policy names no license and gives no
  citation wording.
- Every record in the manifest has `data_utilization_status: Unrestricted` in the search API.
- Each Phytozome genome has a `DataReleasePolicy.html`, listed in the manifest. The three read
  so far say only "This data set is public. Please cite the following publication", and the
  manifest's `citation` field copies that publication. Phytozome also asks users to cite
  Goodstein et al. 2012, Nucleic Acids Research 40(D1):D1178-D1186.
- Phytozome tags TAIR10 and Araport11 `EXT`, sequenced outside JGI. TAIR's
  [licensing page](https://phoenixbioinformatics.atlassian.net/wiki/spaces/COM/pages/42216420/TAIR+Licensing)
  makes its `Public_Data_Releases` folder CC BY 4.0, allows limited excerpts of other data, and
  requires permission to redistribute substantial subsets. Whether TAIR10 is in that folder is
  not yet confirmed, so Arabidopsis files are used only as excerpts until it is.
