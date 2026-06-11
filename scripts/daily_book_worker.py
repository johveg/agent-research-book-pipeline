#!/usr/bin/env python3
"""Daily orchestrator for the Terefo Heal Reboa research book loop."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from research_common import CONFIG_PATH, LOGS, REPORTS, ROOT, connect_db, git_commit_push, init_db, run_id_now, utc_now, write_json

PY = sys.executable


def run(cmd: list[str], log) -> dict:
    log.write('\n$ ' + ' '.join(cmd) + '\n')
    p=subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    log.write(p.stdout)
    if p.stderr: log.write('\n[stderr]\n'+p.stderr)
    return {'cmd':cmd,'returncode':p.returncode,'stdout_tail':p.stdout[-2000:],'stderr_tail':p.stderr[-2000:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", nargs="?", help="Optional explicit run ID")
    ap.add_argument("--manual", action="store_true", help="Run immediately with a manual run ID prefix")
    ap.add_argument("--skip-capture", action="store_true", help="Only run editorial ingestion/update steps on existing sources")
    args = ap.parse_args()
    run_id = args.run_id or (("manual-" + run_id_now()) if args.manual else run_id_now())
    init_db()
    cfg=json.loads(CONFIG_PATH.read_text())
    state_dir=LOGS/'runs'/'state'; state_dir.mkdir(parents=True, exist_ok=True)
    state_path=state_dir/f'{run_id}.state'; latest=state_dir/'latest.state'
    full_log=LOGS/'runs'/f'{run_id}.log'; full_log.parent.mkdir(parents=True, exist_ok=True)
    start=utc_now()
    state=f'RUN_ID={run_id}\nSTATUS=running\nSTARTED_AT={start}\nUPDATED_AT={start}\nFULL_LOG={full_log}\nDELIVERED=0\n'
    state_path.write_text(state); latest.write_text(state)
    steps=[]; status='ok'; error=''
    with full_log.open('a', encoding='utf-8') as log:
        try:
            web_json=LOGS/'runs'/f'{run_id}-web.json'
            li_json=LOGS/'runs'/f'{run_id}-linkedin.json'
            trends_json=LOGS/'runs'/f'{run_id}-trends.json'
            if not args.skip_capture:
                steps.append(run([PY,'scripts/capture_web_daily.py','--run-id',run_id,'--json-out',str(web_json), *sum([['--query',q] for q in cfg['web_queries']], [])], log))
                steps.append(run([PY,'scripts/capture_linkedin_daily.py','--run-id',run_id,'--json-out',str(li_json), *sum([['--query',q] for q in cfg['linkedin_queries']], [])], log))
            else:
                steps.append({'cmd':[PY,'scripts/capture_web_daily.py','--skip-capture'], 'returncode':0, 'stdout_tail':'skipped by --skip-capture', 'stderr_tail':''})
                steps.append({'cmd':[PY,'scripts/capture_linkedin_daily.py','--skip-capture'], 'returncode':0, 'stdout_tail':'skipped by --skip-capture', 'stderr_tail':''})
            steps.append(run([PY,'scripts/extract_entities.py'], log))
            steps.append(run([PY,'scripts/extract_claims.py'], log))
            steps.append(run([PY,'scripts/update_entity_pages.py','--run-id',run_id], log))
            steps.append(run([PY,'scripts/update_claims_page.py','--run-id',run_id], log))
            steps.append(run([PY,'scripts/synthesize_chapters.py','--run-id',run_id], log))
            steps.append(run([PY,'scripts/discover_trends.py','--run-id',run_id,'--json-out',str(trends_json)], log))
            steps.append(run([PY,'scripts/update_book_pages.py','--run-id',run_id], log))
            steps.append(run([PY,'scripts/verify_editorial_ingestion.py'], log))
            # Build a small incremental local vector index. This is local runtime state and not committed.
            steps.append(run([PY,'scripts/build_vector_db.py'], log))
            if any(s['returncode'] not in (0,) for s in steps):
                status='partial'
            summary_md=REPORTS/'daily'/f'{run_id}.md'
            trend_payload=json.loads(trends_json.read_text()) if trends_json.exists() else {'candidates':[]}
            md=['# Daily research book run','',f'- Run: `{run_id}`',f'- Started: {start}',f'- Finished: {utc_now()}',f'- Status: `{status}`','', '## Steps','']
            for s in steps:
                md.append(f"- `{s['cmd'][1] if len(s['cmd'])>1 else s['cmd'][0]}`: exit {s['returncode']}")
            md += ['', '## Trend candidates', '']
            for c in trend_payload.get('candidates',[])[:20]: md.append(f"- **{c['term']}** — {c['count']} mentions")
            md += ['', '## Notes', '', 'LinkedIn capture is read-only and limited to visible authenticated search-result page text. Trend candidates require human review before promotion to recurring search terms.']
            summary_md.write_text('\n'.join(md)+'\n', encoding='utf-8')
            steps.append(run([PY,'scripts/update_claims_page.py','--run-id',run_id], log))
            steps.append(run([PY,'scripts/synthesize_chapters.py','--run-id',run_id], log))
            commit=git_commit_push(f'research: daily book update {run_id}', ['docs','reports','data/search_config.json','data/schema.sql','data/chroma_manifest.json','.github','mkdocs.yml','README.md','.gitignore','.env.example','scripts','tests'])
            write_json(LOGS/'runs'/f'{run_id}-commit.json', commit)
        except Exception as e:
            status='error'; error=type(e).__name__+': '+str(e)
            log.write('\nERROR '+error+'\n')
    end=utc_now()
    with connect_db() as con:
        con.execute('INSERT OR REPLACE INTO runs (id, started_at, ended_at, status, mode, summary_path, error) VALUES (?,?,?,?,?,?,?)',(run_id,start,end,status,'daily',str(REPORTS/'daily'/f'{run_id}.md'),error))
        con.commit()
    final=f'RUN_ID={run_id}\nSTATUS={status}\nSTARTED_AT={start}\nUPDATED_AT={end}\nENDED_AT={end}\nFULL_LOG={full_log}\nSUMMARY_MD={REPORTS/"daily"/f"{run_id}.md"}\nEXIT_CODE={0 if status in ("ok","partial") else 1}\nDELIVERED=0\nERROR={json.dumps(error)}\n'
    state_path.write_text(final); latest.write_text(final)
    print(f'Terefo Heal Reboa book loop finished: {status}\nRun ID: {run_id}\nSummary: {REPORTS/"daily"/f"{run_id}.md"}\nLog: {full_log}')
    return 0 if status in ('ok','partial') else 1
if __name__=='__main__': raise SystemExit(main())
