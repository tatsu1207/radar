#!/usr/bin/env python
"""Download the Medaka consensus models that the pip package does not bundle.

medaka ships only a few R10.4.1 v5 models and downloads any other model on first
use. On servers that cannot reach raw.githubusercontent.com (the URL medaka uses)
that download hangs, so polishing R9.4.1 reads, older Dorado (v4.x) reads or using
--bacteria fails. This fetches every consensus model medaka can map a basecaller
model to, plus the bacterial methylation model, into medaka's model directory.

Each model is tried first at medaka's own URL, then via the GitHub API + Git LFS
(api.github.com / github-cloud.githubusercontent.com), which some networks allow
when raw.githubusercontent.com is blocked. Files are checked against the LFS sha256
when that route is used. Existing models are skipped.

Run with the radar-medaka environment's Python:
    conda run -n radar-medaka python backend/scripts/fetch_medaka_models.py [--dest DIR]
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

import medaka.options as mo

REPO = "nanoporetech/medaka"
TIMEOUT = 60


def _get(url, headers=None, data=None, timeout=TIMEOUT):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _direct(fname):
    url = mo.model_url_template.format(pkg="medaka", subdir="data", fname=fname)
    data = _get(url, timeout=15)
    if data.startswith(b"version https://git-lfs"):
        raise ValueError("got an LFS pointer, not the model")
    return data


def _via_lfs(fname):
    pointer = _get(f"https://api.github.com/repos/{REPO}/contents/medaka/data/{fname}",
                   headers={"Accept": "application/vnd.github.raw"}).decode()
    fields = dict(line.split(" ", 1) for line in pointer.strip().splitlines())
    oid = fields["oid"].split(":", 1)[1]
    size = int(fields["size"])
    body = json.dumps({"operation": "download", "transfers": ["basic"],
                       "objects": [{"oid": oid, "size": size}]}).encode()
    batch = json.loads(_get(f"https://github.com/{REPO}.git/info/lfs/objects/batch", data=body,
                            headers={"Accept": "application/vnd.git-lfs+json",
                                     "Content-Type": "application/vnd.git-lfs+json"}))
    href = batch["objects"][0]["actions"]["download"]["href"]
    data = _get(href)
    if len(data) != size or hashlib.sha256(data).hexdigest() != oid:
        raise ValueError("size/sha256 mismatch")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=str(mo.model_stores[0]),
                    help="model directory (default: medaka's package data directory)")
    args = ap.parse_args()
    os.makedirs(args.dest, exist_ok=True)

    models = sorted({c for c, _ in mo.basecaller_models.values() if c} | {mo.bact_methyl_model})
    failed = []
    routes = [_direct, _via_lfs]
    for m in models:
        fname = f"{m}_model_pt.tar.gz"
        out = os.path.join(args.dest, fname)
        if any(os.path.exists(os.path.join(str(s), fname)) for s in mo.model_stores) or os.path.exists(out):
            print(f"  have  {m}")
            continue
        data = None
        for fetch in list(routes):
            try:
                data = fetch(fname)
                break
            except Exception as e:  # noqa: BLE001 - try the next route
                err = e
                if fetch is _direct and len(routes) > 1:
                    routes.remove(_direct)  # blocked here: don't wait on it for every model
        if data is None:
            print(f"  FAIL  {m}: {err}")
            failed.append(m)
            continue
        with open(out + ".part", "wb") as f:
            f.write(data)
        os.replace(out + ".part", out)
        print(f"  got   {m} ({len(data) // 1024} kB)")
    print(f"{len(models) - len(failed)}/{len(models)} models available in {args.dest}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
