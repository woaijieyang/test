"""Bounded durable frozen inputs. Images remain in the original observation archive."""
import fcntl,hashlib,json,threading
from pathlib import Path
from .storage.store import canonical,IntegrityError,_write_immutable,_verify_ref

def frozen_to_record(item):
    return dict(packet=json.loads(item.packet_json),receipt=json.loads(item.receipt_json),
        mapping=None if item.mapping_json is None else json.loads(item.mapping_json),episode_instance=item.episode_instance)

def frozen_from_record(row):
    from .async_admission import FrozenObservation
    from graphAdapter.observation_packet import ObservationPacket
    from poseAdapter.interfaces.mapping import MappingSample
    sample=None if row['mapping'] is None else MappingSample.from_record(row['mapping'])
    return FrozenObservation.create(ObservationPacket(**row['packet']),row['receipt'],
        mapping_sample=sample,episode_instance=row['episode_instance'])

class FrozenTailJournal:
    def __init__(self,root,job,*,max_bytes,max_entries):
        if any(type(v)is not int or v<=0 for v in (max_bytes,max_entries)):raise ValueError('Positive journal limits required')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.owner=threading.get_ident();self.lock=(self.root/'writer.lock').open('a+b')
        self.failed=False;self.job=job;self.max_bytes=max_bytes;self.max_entries=max_entries
        self.entries=[];self.items=[];self.intents={};self.intent_refs={};self.bytes=0;self.head=job.digest
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            _write_immutable(self.root,'identity.json',canonical(dict(schema_version=2,job_sha256=job.digest,
                base_snapshot_id=job.record['base_snapshot_id'],max_bytes=max_bytes,max_entries=max_entries)))
            intents=sorted((self.root/'intents').glob('*.json'))
            if len(intents)>max_entries:raise IntegrityError('Journal exceeds intent budget')
            for path in intents:
                size=path.stat().st_size
                if self.bytes+size>max_bytes:raise IntegrityError('Journal exceeds byte budget')
                payload=path.read_bytes();row=json.loads(payload)
                body=row['body']
                if row['sha256']!=hashlib.sha256(canonical(body)).hexdigest() or body['job_sha256']!=job.digest:
                    raise IntegrityError('Frozen intent hash differs')
                item=frozen_from_record(body['observation']);seq=item.packet.capture_seq
                expected=job.record['base_cutoff']['capture_seq']+len(self.intents)+1
                if seq!=expected or path.name!=f'{seq:010d}.json':raise IntegrityError('Intent sequence differs')
                if item.packet.episode_uid!=job.record['episode_uid'] or item.episode_instance!=job.record['episode_instance']:
                    raise IntegrityError('Intent session differs')
                self.intents[seq]=item;self.intent_refs[seq]=dict(path='intents/'+path.name,sha256=hashlib.sha256(payload).hexdigest(),bytes=size)
                self.bytes+=size
            paths=sorted((self.root/'entries').glob('*.json'))
            if len(paths)>max_entries:raise IntegrityError('Journal exceeds entry budget')
            for path in paths:
                size=path.stat().st_size
                if self.bytes+size>max_bytes:raise IntegrityError('Journal exceeds byte budget')
                row=json.loads(path.read_bytes());self._accept(row,path.name,size)
            if len(self.intents)>len(self.entries)+1:raise IntegrityError('Multiple unbound frozen intents')
        except BaseException:self.lock.close();self.lock=None;raise
    def _owner(self):
        if self.lock is None:raise RuntimeError('Journal is closed')
        if threading.get_ident()!=self.owner:raise RuntimeError('Journal requires its owning writer thread')
        if self.failed:raise RuntimeError('Journal write failed; reopen to recover durable state')
    def _accept(self,row,name,size):
        body=row['body'];digest=hashlib.sha256(canonical(body)).hexdigest()
        if digest!=row['sha256'] or body['previous']!=self.head or body['job_sha256']!=self.job.digest:
            raise IntegrityError('Frozen journal hash chain differs')
        ref=body['observation_ref'];payload=json.loads(_verify_ref(self.root,ref).read_bytes())
        item=frozen_from_record(payload['body']['observation']);packet=item.packet
        if self.intent_refs.get(packet.capture_seq)!=ref:raise IntegrityError('Commit references another intent')
        expected=self.job.record['base_cutoff']['capture_seq']+len(self.items)+1
        if packet.capture_seq!=expected or name!=f'{expected:010d}.json':raise IntegrityError('Frozen journal has a gap or reordered entry')
        if packet.episode_uid!=self.job.record['episode_uid'] or item.episode_instance!=self.job.record['episode_instance']:
            raise IntegrityError('Frozen journal session differs')
        self.entries.append(row);self.items.append(item);self.bytes+=size;self.head=digest
    def prepare(self,item):
        """Persist exactly one pending frozen input before publishing its graph."""
        self._owner();observation=frozen_to_record(item);checked=frozen_from_record(observation)
        packet=checked.packet;seq=packet.capture_seq
        if packet.episode_uid!=self.job.record['episode_uid'] or checked.episode_instance!=self.job.record['episode_instance']:
            raise IntegrityError('Intent session differs')
        if seq in self.intents:
            if frozen_to_record(self.intents[seq])!=observation:raise IntegrityError('Conflicting frozen intent retry')
            return self.intent_refs[seq]
        expected=self.job.record['base_cutoff']['capture_seq']+len(self.entries)+1
        if seq!=expected or len(self.intents)!=len(self.entries):raise IntegrityError('Previous intent must be bound before another input')
        body=dict(job_sha256=self.job.digest,observation=observation)
        data=canonical(dict(body=body,sha256=hashlib.sha256(canonical(body)).hexdigest()))
        relative=f'intents/{seq:010d}.json'
        ref=dict(path=relative,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        # Reserve the exact fixed-size commit envelope before graph publication.
        commit=self._commit_row(ref,'0'*64)
        if len(self.intents)>=self.max_entries or self.bytes+len(data)+len(canonical(commit))>self.max_bytes:
            raise ValueError('Frozen journal capacity exhausted; do not drop or overwrite inputs')
        try:
            _write_immutable(self.root,relative,data)
            self.intents[seq]=checked;self.intent_refs[seq]=ref;self.bytes+=len(data)
        except BaseException:self.failed=True;raise
        return ref
    def _commit_row(self,ref,snapshot_id):
        body=dict(job_sha256=self.job.digest,previous=self.head,snapshot_id=snapshot_id,observation_ref=ref)
        return dict(body=body,sha256=hashlib.sha256(canonical(body)).hexdigest())
    def pending(self):
        self._owner();seq=self.job.record['base_cutoff']['capture_seq']+len(self.entries)+1
        return self.intents.get(seq)
    def reconcile(self,committed_reader):
        """Bind a persisted input only if its exact publication is now visible."""
        self._owner();item=self.pending()
        if item is None:return False
        if committed_reader.cutoff['capture_seq']<item.packet.capture_seq:return False
        return self.append(item,committed_reader)
    def append(self,item,committed_reader):
        self._owner()
        from .storage.final_snapshot import plain
        packet=item.packet
        if committed_reader.identity['episode_uid']!=self.job.record['episode_uid']:
            raise IntegrityError('Committed journal source episode differs')
        if dict(committed_reader.cutoff)!=dict(capture_seq=packet.capture_seq,event_seq=packet.event_seq):
            raise IntegrityError('Journal requires the exact committed observation frontier')
        capture=committed_reader.get_view(packet.frame_uid)['capture'];record=packet.to_record()
        if canonical(plain({k:capture[k] for k in record}))!=canonical(record):raise IntegrityError('Frozen journal packet differs from committed raw facts')
        observation=frozen_to_record(item);frozen_from_record(observation)
        index=packet.capture_seq-self.job.record['base_cutoff']['capture_seq']-1
        if 0<=index<len(self.entries):
            prior=self.entries[index]['body']
            if frozen_to_record(self.items[index])!=observation or prior['snapshot_id']!=committed_reader.snapshot_id:
                raise IntegrityError('Conflicting retry of frozen journal entry')
            return False
        if index!=len(self.entries):raise IntegrityError('Journal append is not consecutive')
        if item.episode_instance!=self.job.record['episode_instance']:raise IntegrityError('Journal session differs')
        ref=self.prepare(item)
        row=self._commit_row(ref,committed_reader.snapshot_id);data=canonical(row)
        if len(self.entries)>=self.max_entries or self.bytes+len(data)>self.max_bytes:
            raise ValueError('Frozen journal capacity exhausted; do not drop or overwrite inputs')
        name=f'{packet.capture_seq:010d}.json'
        try:
            _write_immutable(self.root,'entries/'+name,data)
            self._accept(row,name,len(data))
        except BaseException:self.failed=True;raise
        return True
    def snapshot(self):self._owner();return tuple(self.items)
    def close(self):
        if self.lock is not None:
            if threading.get_ident()!=self.owner:raise RuntimeError('Journal must close on its owning writer thread')
            self.lock.close();self.lock=None
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
