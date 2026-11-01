"""Verify public file hashes and the row counts of exported SQLite journals."""
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
manifest = json.loads((ROOT / 'experiments/manifest.json').read_text(encoding='utf-8'))
errors = []
seen = set()
for entry in manifest['entries']:
    record = entry['public']
    relative = record['path']
    if relative in seen:
        errors.append(f'duplicate: {relative}')
    seen.add(relative)
    path = ROOT / relative
    if not path.is_file():
        errors.append(f'missing: {relative}')
        continue
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            size += len(block)
            digest.update(block)
    if digest.hexdigest() != record['sha256'] or size != record['bytes']:
        errors.append(f'file digest or size: {relative}')
    transform = entry['transformation']
    if transform['type'] == 'unchanged' and (record['sha256'] != entry['original_sha256'] or size != entry['original_bytes']):
        errors.append(f'unchanged source mismatch: {relative}')
    if transform['type'] == 'sqlite_to_jsonl':
        counts = {}
        try:
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    row = json.loads(line)
                    if row['record'] == 'row':
                        counts[row['table']] = counts.get(row['table'], 0) + 1
                        for value in row['values']:
                            if isinstance(value, dict) and '$sqlite_blob_base64' in value:
                                base64.b64decode(value['$sqlite_blob_base64'], validate=True)
            counts = {table: counts.get(table, 0) for table in transform['table_rows']}
            if counts != transform['table_rows']:
                errors.append(f'SQLite row counts: {relative}')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f'SQLite JSONL: {relative}: {exc}')
actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'experiments/evidence').rglob('*') if p.is_file()}
if actual != seen:
    errors.append(f'unlisted or missing files: {len(actual - seen)} unlisted, {len(seen - actual)} missing')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print(f'Verified {len(seen)} files, including {sum(e["transformation"]["type"] == "sqlite_to_jsonl" for e in manifest["entries"])} SQLite exports.')
