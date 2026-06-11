#!/usr/bin/env python3
"""Build or refresh a local ChromaDB vector index over sanitized Markdown artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_common import ROOT, RAW, DOCS, REPORTS, sha256_text, utc_now, write_json


def chunks(text: str, size=1200, overlap=150):
    text=' '.join(text.split())
    i=0
    while i < len(text):
        yield text[i:i+size]
        i += max(1, size-overlap)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--limit', type=int, default=0); args=ap.parse_args()
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        print(json.dumps({'status':'missing_dependency','error':str(e)})); return 2
    paths=[]
    for base in [DOCS, RAW/'web', RAW/'linkedin', REPORTS/'discovery']:
        if base.exists(): paths.extend(base.rglob('*.md'))
    paths=sorted(set(paths))
    if args.limit: paths=paths[:args.limit]
    client=chromadb.PersistentClient(path=str(ROOT/'vector_db'))
    coll=client.get_or_create_collection('terefohealreboa')
    model=SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
    ids=[]; docs=[]; metas=[]
    for p in paths:
        txt=p.read_text(errors='ignore')
        for idx,ch in enumerate(chunks(txt)):
            if len(ch)<80: continue
            cid='md_'+sha256_text(str(p.relative_to(ROOT))+str(idx)+ch)[:32]
            ids.append(cid); docs.append(ch); metas.append({'path':str(p.relative_to(ROOT)), 'chunk':idx, 'source_type':'markdown'})
            if len(ids)>=64:
                emb=model.encode(docs, normalize_embeddings=True).tolist()
                coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=emb)
                ids=[]; docs=[]; metas=[]
    if ids:
        emb=model.encode(docs, normalize_embeddings=True).tolist()
        coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=emb)
    manifest={'built_at':utc_now(),'collection':'terefohealreboa','count':coll.count(),'indexed_markdown_files':len(paths)}
    write_json(ROOT/'data/chroma_manifest.json', manifest)
    print(json.dumps(manifest, indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())
