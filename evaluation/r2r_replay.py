"""Extract exact source-only queries from the supplied impact workbook.

Read-only OOXML, no spreadsheet dependency or formula execution. Only task key,
original instruction and row location are exported: no scores, advice or trace.
Usage: python -m evaluation.r2r_replay workbook.xlsx --records /outside/records.json
Then: python -m tools.r2r_authoring.audit --records /outside/records.json --output /outside/audit.json
The workbook remains external to the runtime and repository teaching assets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def extract(path: Path) -> tuple[list[dict], dict]:
    raw=path.read_bytes()
    with ZipFile(path) as archive:
        links={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        sheet=next((s for s in workbook.findall('s:sheets/s:sheet',NS) if s.get('name')=='指令问题定位'),None)
        if sheet is None:raise ValueError('Missing instruction evidence sheet')
        target=links[sheet.attrib[REL]].lstrip('/')
        target=target if target.startswith('xl/') else 'xl/'+target
        if '..' in PurePosixPath(target).parts:raise ValueError('Invalid worksheet member')
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(t.text or '' for t in si.findall('.//s:t',NS)) for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        header=None;records=[];seen=set()
        for row in ET.fromstring(archive.read(target)).findall('s:sheetData/s:row',NS):
            cells={}
            for cell in row:
                col=''.join(c for c in cell.get('r','') if c.isalpha())
                value=cell.find('s:v',NS);value=None if value is None else value.text
                if cell.get('t')=='inlineStr':value=''.join(t.text or '' for t in cell.findall('.//s:t',NS))
                elif cell.get('t')=='s':value=strings[int(value)]
                cells[col]=value
            if '任务键' in cells.values() and '原始 Instruction' in cells.values():
                header={v:k for k,v in cells.items() if v};continue
            if header is None:continue
            key=cells.get(header['任务键']);source=cells.get(header['原始 Instruction'])
            if not key and not source:continue
            if not key or not isinstance(source,str):raise ValueError('Missing task identity/source')
            pieces=key.split('|')
            if len(pieces)<5 or pieces[0]!='r2r' or pieces[2]!='en':raise ValueError('Non-R2R-English task')
            if key in seen:raise ValueError('Duplicate task key')
            seen.add(key)
            records.append(dict(task_id=key,original_instruction=source,split=pieces[1],source={'scene_id':pieces[3]},workbook_row=int(row.attrib['r'])))
    if not records:raise ValueError('No source records')
    return records,dict(workbook_sha256=hashlib.sha256(raw).hexdigest(),sheet='指令问题定位',count=len(records),
        fields_used=['任务键','原始 Instruction'],path_ids_available=False,
        caveat='No trajectory identity inferred from episode IDs. Development replay, not held-out navigation evaluation.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('workbook',type=Path);p.add_argument('--records',required=True,type=Path);a=p.parse_args()
    records,origin=extract(a.workbook)
    a.records.parent.mkdir(parents=True,exist_ok=True)
    a.records.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(origin,ensure_ascii=False))
if __name__=='__main__':main()
