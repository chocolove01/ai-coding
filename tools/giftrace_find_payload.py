#!/usr/bin/env python3
import argparse, hashlib, struct
from pathlib import Path

FMT = '<IHHQQIIIII6I'
HSZ = struct.calcsize(FMT)
MAGIC = 0x32544647


def read_trace(path: Path):
    rows=[]
    with path.open('rb') as f:
        idx=0
        while True:
            h=f.read(HSZ)
            if not h:
                break
            if len(h)!=HSZ:
                raise SystemExit(f'truncated header at record {idx}')
            v=struct.unpack(FMT,h)
            magic,ver,typ,seq,cycle,pc,madr,tadr,qwc,nbytes,*p=v
            if magic!=MAGIC or ver!=2:
                raise SystemExit(f'bad record {idx}: magic={magic:08x} version={ver}')
            payload=f.read(nbytes)
            if len(payload)!=nbytes:
                raise SystemExit(f'truncated payload at record {idx}')
            rows.append(dict(index=idx,type=typ,seq=seq,cycle=cycle,pc=pc,madr=madr,tadr=tadr,qwc=qwc,nbytes=nbytes,p=p,payload=payload))
            idx+=1
    return rows


def collect_dma(rows):
    seen=set(); segs=[]; stream=bytearray()
    for r in rows:
        if r['type']!=1 or not r['payload']:
            continue
        digest=hashlib.sha256(r['payload']).digest()
        key=(r['seq'],r['madr'],r['nbytes'],digest)
        if key in seen:
            continue
        seen.add(key)
        start=len(stream)
        stream.extend(r['payload'])
        segs.append(dict(start=start,end=len(stream),record=r))
    return bytes(stream),segs


def map_ranges(segs,start,end):
    out=[]
    for s in segs:
        a=max(start,s['start']); b=min(end,s['end'])
        if a>=b:
            continue
        r=s['record']; local=a-s['start']
        out.append(dict(seq=r['seq'],record=r['index'],madr=r['madr'],ee_start=(r['madr']+local)&0xffffffff,
                        length=b-a,pc=r['pc'],tadr=r['tadr'],qwc=r['qwc'],chcr=r['p'][1] if len(r['p'])>1 else 0))
    return out


def main():
    ap=argparse.ArgumentParser(description='Find exact raw payload SHA in PCSX2 GFT2 DMA records and map it to EE MADR ranges.')
    ap.add_argument('trace', type=Path)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--sha256', help='target SHA-256 hex; requires --size')
    g.add_argument('--file', type=Path, help='exact target payload file')
    ap.add_argument('--size', type=int, help='target byte size when --sha256 is used')
    ap.add_argument('--alignment', type=int, default=16, help='scan alignment (default 16; use 1 for byte-wise)')
    args=ap.parse_args()
    if args.sha256:
        if not args.size or args.size<=0:
            ap.error('--sha256 requires positive --size')
        target_sha=args.sha256.lower(); target_size=args.size
        if len(target_sha)!=64:
            ap.error('--sha256 must be 64 hex chars')
    else:
        target=args.file.read_bytes(); target_size=len(target); target_sha=hashlib.sha256(target).hexdigest()
    if args.alignment<=0:
        ap.error('--alignment must be positive')

    rows=read_trace(args.trace)
    stream,segs=collect_dma(rows)
    print(f'trace_records={len(rows)} dma_segments={len(segs)} concatenated_bytes={len(stream)}')
    print(f'target_size={target_size} target_sha256={target_sha} alignment={args.alignment}')
    if target_size>len(stream):
        raise SystemExit('NO MATCH: target larger than concatenated DMA stream')

    matches=[]
    for off in range(0,len(stream)-target_size+1,args.alignment):
        if hashlib.sha256(stream[off:off+target_size]).hexdigest()==target_sha:
            matches.append(off)
    if not matches and args.alignment!=1:
        print('no aligned match; retry with --alignment 1 if needed')
    if not matches:
        raise SystemExit('NO MATCH')

    for mi,off in enumerate(matches,1):
        end=off+target_size
        print(f'MATCH {mi}: stream=[0x{off:x},0x{end:x})')
        for m in map_ranges(segs,off,end):
            print('  '
                  f"record={m['record']} seq={m['seq']} "
                  f"EE=[0x{m['ee_start']:08x},0x{(m['ee_start']+m['length']):08x}) len={m['length']} "
                  f"MADR=0x{m['madr']:08x} TADR=0x{m['tadr']:08x} QWC={m['qwc']} "
                  f"CHCR=0x{m['chcr']:08x} PC=0x{m['pc']:08x}")

if __name__=='__main__':
    main()
