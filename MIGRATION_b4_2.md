# b4_2 → single-instance migration runbook

Migrate user **b4_2**'s data from their old Docker stack into the new bare-metal
RADAR instance owned by `wgs`, then decommission the old stack.

Status: **PLAN — not yet executed.** Review before running anything irreversible
(Phase 6 only).

---

## Facts (measured 2026-10-23)

| Item | Value |
|---|---|
| Old stack | Docker project `radar-b4_2` (containers `radar-b4_2-*`, running) |
| Old DB | container `radar-b4_2-db-1`, PostgreSQL **16**, db `radar`, user `radar` |
| Old data volume | `radar-b4_2_radar-data` → `/data` (uploads + results) |
| Raw uploads | **106.6 GB** at `/data/uploads/<sample_id>/...` — MUST migrate |
| Results | **146.1 GB** at `/data/results/...` — regenerable, do NOT migrate |
| DB contents | 1 project ("Default", id `6692550c-3e1d-4213-b99e-6dfd60add161`), 87 samples, 192 sample_files, 68 complete |
| New instance | bare-metal, PostgreSQL **18.6** on port 8223, db `radar`, OS user `wgs` |
| New uploads dir | `/home/wgs/radar/data/uploads/<sample_id>/...` |
| New ownership | `projects.user_id` → `users.id` (nullable FK). Samples/results cascade from project. |

## Strategy — why "re-ingest + re-run", not "restore the DB"

The new schema is 169 commits ahead: many new result tables, `hazard_rank`
replaces the old 0–10 composite risk, `arg element_type`, metadata host/lat-lon,
etc. Old result rows have **no clean mapping** to the new tables, and PG16→PG18
full restore would drag the old schema in. So:

- **Migrate only the raw inputs + ingestion rows** (projects, samples,
  sample_files, metadata) and **re-run the pipeline** on the new instance.
- This copies only **~107 GB** (uploads), not 253 GB, and regenerates all
  results in the **new format with the fixed/better pipeline** (Plassembler,
  dnaapler, fixed Medaka, hazard rank, and the space-in-filename fix).
- Old results stay available in the archived old stack during transition.

Trade-off: re-running 87 samples through assembly+annotation is CPU-heavy
(hours–days). Batch it; prioritise the samples b4_2 actually needs.

---

## Pre-flight

- [ ] Free disk ≥ ~130 GB (uploads 107 GB + working headroom). Currently ~290 GB free. OK.
- [ ] New instance up (`./start.sh` done, 8203/8213/8223/8233 listening).
- [ ] Confirm with b4_2 which samples are priority for re-analysis.

## Phase 0 — Back up the old stack (safety net, reversible)

```bash
# Logical DB dump of the old Postgres (small)
docker exec radar-b4_2-db-1 pg_dump -U radar -d radar -Fc \
  > /home/wgs/radar/backups/b4_2_olddb_$(date +%Y%m%d).dump
# (uploads/results already persist in the docker volume radar-b4_2_radar-data;
#  do NOT delete that volume until Phase 6 verification passes)
```

Leave the old stack **running** (or `docker compose stop` it — volume data persists either way).

## Phase 1 — Create the b4_2 account in the new instance

b4_2 registers at `http://<host>:8203` (or wgs registers on their behalf), then:

```bash
cd /home/wgs/radar && source data/ports.env
source /home/wgs/miniforge3/etc/profile.d/conda.sh && conda activate radar
# Get the new user id
psql -h localhost -p "$PORT_PG" -U wgs -d radar \
  -tc "SELECT id, username FROM users WHERE username='b4_2';"
```
Record `B4_2_UID`.

## Phase 2 — Copy raw uploads (old volume → new dir)

```bash
# Stream uploads out of the docker volume into the new uploads dir.
# Per-sample subdirs are keyed by sample UUID, identical on both sides.
docker run --rm \
  -v radar-b4_2_radar-data:/old:ro \
  -v /home/wgs/radar/data:/new \
  alpine sh -c 'cp -an /old/uploads/. /new/uploads/'
# verify size (~107 GB) and a sample count
du -sh /home/wgs/radar/data/uploads
ls /home/wgs/radar/data/uploads | wc -l
```
`cp -an` = archive, no-clobber (safe to re-run/resume).

## Phase 3 — Port ingestion rows (projects / samples / sample_files / metadata)

Only these 4 tables; results are regenerated. **sample_files.file_path must be
rewritten** from `/data/...` → `/home/wgs/radar/data/...`.

1. **Diff columns first** (schemas may differ) — for each table compare old vs new:
   ```bash
   docker exec radar-b4_2-db-1 psql -U radar -d radar -c "\d projects"
   psql -h localhost -p "$PORT_PG" -U wgs -d radar -c "\d projects"
   # repeat for samples, sample_files, metadata — note added/removed/renamed cols
   ```
2. **Export the 4 tables as CSV** from the old DB (explicit shared columns only):
   ```bash
   for t in projects samples sample_files metadata; do
     docker exec radar-b4_2-db-1 psql -U radar -d radar \
       -c "\copy (SELECT * FROM $t) TO STDOUT WITH CSV HEADER" \
       > /home/wgs/radar/backups/b4_2_${t}.csv
   done
   ```
3. **Load into the new DB** with a small transform (do in a transaction). Outline:
   - Insert the project row, set `user_id = B4_2_UID` (rename "Default" → e.g. "b4_2 (imported)" to avoid clashing with the new instance's own Default project).
   - Insert samples (keep UUIDs; set `status='pending'` so they are re-runnable; drop any columns that no longer exist).
   - Insert sample_files with `REPLACE(file_path,'/data/','/home/wgs/radar/data/')`.
   - Insert metadata rows (map host/lat-lon if present, else leave new cols NULL).
   - Load CSVs with explicit column lists so new-schema defaults fill the rest.
   > This step is schema-dependent — reconcile against the Phase-3.1 column diff at execution time. Keep it in one `BEGIN; … COMMIT;` so a mismatch rolls back cleanly.
4. **Verify**:
   ```bash
   psql -h localhost -p "$PORT_PG" -U wgs -d radar -c \
     "SELECT p.name, count(s.*) FROM projects p LEFT JOIN samples s ON s.project_id=p.id GROUP BY p.name;"
   # spot-check that sample_files.file_path now points to existing files
   ```

## Phase 4 — Re-run the pipeline (batched)

In the new UI (logged in as b4_2) or via the API, trigger analysis on the
imported samples. Start with a **1–2 sample smoke batch**, confirm results look
right (species, ARGs, hazard rank, and that a spaced-filename sample now passes),
then batch the rest. The pipeline worker runs `concurrency=2`, so queue in
groups and let it churn.

## Phase 5 — Verify before deleting anything

- [ ] b4_2 can log in and see their project + samples.
- [ ] Smoke-batch samples complete with sensible results.
- [ ] The previously-failing hybrid/spaced-filename sample now succeeds.
- [ ] b4_2 signs off that nothing critical is missing (old results still in the archived stack for comparison).

## Phase 6 — Decommission old stack (reclaims 271 GB) — IRREVERSIBLE

Only after Phase 5 sign-off:
```bash
cd /home/b4_2/radar 2>/dev/null || true
docker compose -p radar-b4_2 down            # stop + remove containers (keeps volumes)
# After final confirmation, remove the volumes (THIS deletes the 271 GB):
docker volume rm radar-b4_2_radar-data radar-b4_2_pgdata radar-b4_2_radar-databases
docker image prune -f
```
Keep `backups/b4_2_olddb_*.dump` and the uploads (now in the new instance).

---

## Rollback

- Before Phase 6, the old stack is fully intact — `docker compose -p radar-b4_2 up -d`
  brings b4_2's old instance back on ports 8202/8212/8222/8232.
- Phase 3 load runs in a transaction; a bad load rolls back without touching the
  new instance's own data.

## Open decisions for wgs

1. Re-run **all 87** samples, or only b4_2's priority subset? (compute cost)
2. Import project named "b4_2 (imported)" vs merge into b4_2's own new Default?
3. Timing of Phase 6 (how long to keep the old stack as a safety archive).
