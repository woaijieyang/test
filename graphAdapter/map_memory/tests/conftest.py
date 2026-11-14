"""Fault injection into owned fixture pages; preserves original bytes on teardown."""
from pathlib import Path
import sqlite3,zlib,pytest
from graphAdapter.map_memory.storage.pages import SelectiveReader
@pytest.fixture
def tamper_page():
    changes=[]
    def alter(root,revision,path):
        reader=SelectiveReader(root,revision)
        try:
            descriptor=["r",reader.root_node];key=None
            for part in path:
                key=descriptor[1]
                descriptor=reader.map_key(key,part)if isinstance(part,str)else reader.sequence_index(key,part)
            if descriptor[0]=="r":key=descriptor[1]
        finally:reader.close()
        db=sqlite3.connect(Path(root)/"pages.sqlite3")
        try:
            original=db.execute("SELECT data FROM nodes WHERE id=?",(key,)).fetchone()[0]
            db.execute("UPDATE nodes SET data=? WHERE id=?",(zlib.compress(b"[]"),key));db.commit()
            changes.append((Path(root),key,original))
        finally:db.close()
    yield alter
    for root,key,data in reversed(changes):
        db=sqlite3.connect(root/"pages.sqlite3")
        try:db.execute("UPDATE nodes SET data=? WHERE id=?",(data,key));db.commit()
        finally:db.close()
