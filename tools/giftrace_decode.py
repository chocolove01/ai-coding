#!/usr/bin/env python3
import argparse, json, struct
from pathlib import Path

FMT = '<IHHQQIIIII6I'
SIZE = struct.calcsize(FMT)
MAGIC = 0x32544647

def main():
    ap = argparse.ArgumentParser(description='Decode PCSX2 LocalizationRuntime v2 .gft traces')
    ap.add_argument('trace')
    ap.add_argument('-o', '--out-dir', default=None)
    args = ap.parse_args()
    src = Path(args.trace)
    out = Path(args.out_dir) if args.out_dir else src.with_suffix(src.suffix + '.decoded')
    out.mkdir(parents=True, exist_ok=True)
    rows=[]
    with src.open('rb') as f:
        index=0
        while True:
            raw=f.read(SIZE)
            if not raw:
                break
            if len(raw)!=SIZE:
                raise SystemExit(f'truncated header at record {index}')
            v=struct.unpack(FMT, raw)
            magic,ver,typ,seq,cycle,pc,madr,tadr,qwc,nbytes,*p=v
            if magic != MAGIC or ver != 2:
                raise SystemExit(f'bad record {index}: magic={magic:08x} version={ver}')
            payload=f.read(nbytes)
            if len(payload)!=nbytes:
                raise SystemExit(f'truncated payload at record {index}')
            row={'index':index,'type':typ,'seq':seq,'cycle':cycle,'pc':f'0x{pc:08x}',
                 'madr':f'0x{madr:08x}','tadr':f'0x{tadr:08x}','qwc':qwc,'bytes':nbytes}
            if typ==1:
                reason,chcr,*_=p
                row.update(reason=reason,chcr=f'0x{chcr:08x}')
                name=f'{index:06d}_seq{seq}_madr{madr:08x}_{nbytes}.bin'
                (out/name).write_bytes(payload)
                row['payload']=name
            elif typ==2:
                dbp,dbw,dpsm,dims,pos,xdir=p
                row.update(dbp=f'0x{dbp:x}',dbw=dbw,dpsm=dpsm,
                           width=dims & 0xffff,height=(dims>>16)&0xffff,
                           dsax=pos & 0xffff,dsay=(pos>>16)&0xffff,xdir=xdir)
            rows.append(row)
            index+=1
    (out/'records.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'{len(rows)} records -> {out}')

if __name__=='__main__':
    main()
