import json, urllib.parse, urllib.request, sys, time

TYPES = ["Structural Annotation GFF","Functional Annotation GFF","Prodigal Annotation GFF",
 "Genemark Annotation GFF","Pfam Annotation GFF","KO_EC Annotation GFF","CRT Annotation GFF",
 "TRNA Annotation GFF","RFAM Annotation GFF","TIGRFam Annotation GFF","SMART Annotation GFF",
 "SUPERFam Annotation GFF","CATH FunFams (Functional Families) Annotation GFF",
 "Clusters of Orthologous Groups (COG) Annotation GFF"]
BASE = "https://api.microbiomedata.org/nmdcschema/data_object_set"

def fetch(t, pages=3, size=200):
    out, tok = [], None
    for _ in range(pages):
        f = urllib.parse.quote(json.dumps({"data_object_type": {"$eq": t}}))
        u = f"{BASE}?filter={f}&max_page_size={size}"
        if tok: u += f"&page_token={tok}"
        req = urllib.request.Request(u, headers={"User-Agent": "curl/8.7.1", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
        out += d.get("resources", [])
        tok = d.get("next_page_token")
        if not tok: break
    return out

res = {}
for t in TYPES:
    try:
        rows = [r for r in fetch(t) if r.get("file_size_bytes") and r.get("url")]
        if not rows:
            print(f"NONE\t{t}", file=sys.stderr); continue
        sm = min(rows, key=lambda r: r["file_size_bytes"])
        res[t] = {"id": sm["id"], "name": sm["name"], "bytes": sm["file_size_bytes"],
                  "md5": sm.get("md5_checksum"), "url": sm["url"],
                  "was_generated_by": sm.get("was_generated_by"), "sampled": len(rows)}
        print(f"{sm['file_size_bytes']:>12,}  {t}  ({len(rows)} sampled)", file=sys.stderr)
    except Exception as e:
        print(f"ERR\t{t}\t{e}", file=sys.stderr)
    time.sleep(0.3)

json.dump(res, open("nmdc_gff_smallest.json","w"), indent=2)
print(f"\nwrote {len(res)} types", file=sys.stderr)
