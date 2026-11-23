"""Explicit field mapping for existing rollout logs; no fabricated target labels."""
from __future__ import annotations
from pathlib import Path
from .artifacts import digest,identity,read_records,training_path
from .data import route_key


def field(row,path):
    value=row
    for key in path.split('.'):
        if isinstance(value,list):value=value[int(key)]
        else:value=value[key]
    return value


def extract_rollout(source,routes,mapping):
    """Map recorded events using audited field paths and literal provenance only.

    Required mapping keys point to actual fields; fixed split/dataset/route IDs
    must come from the supplied official route index, not from guessed language.
    Image paths are resolved relative to the log file unless already absolute.
    """
    source=training_path(source);rows=read_records(source);lookup={route_key(r):r for r in routes}
    required={'event_id','rollout_id','call_id','prompt','image_paths','image_call_ids','protocol_identity'}
    if not required<=set(mapping.get('fields',{})):raise ValueError('rollout field mapping incomplete')
    if 'route_key' not in mapping['fields'] and not mapping.get('route_join'):
        raise ValueError('route_key field or explicit official-identity join required')
    accepted=[];rejected=[];source_sha=digest(source)
    for i,row in enumerate(rows):
        try:
            if any(field(row,k)!=v for k,v in mapping.get('where',{}).items()):continue
            # Never relabel an evaluation trace, even when numeric episode IDs
            # happen to overlap a train annotation or the filename looks like train.
            for key in ('source_split','split'):
                if key in row and row[key]!='train':raise ValueError('ROLLOUT_SPLIT_NOT_TRAIN')
            task=row.get('task_key')
            if task is not None:
                parts=task.split('|')
                if len(parts)!=6 or parts[1]!='train':raise ValueError('NATIVE_TRACE_IS_NOT_TRAIN')
            # An official TRAIN route join alone cannot prove that the frames
            # came from a TRAIN rollout: different splits can share IDs or a
            # scene.  Accept only an explicit recorded split or native task key.
            if task is None and not any(row.get(k)=='train' for k in ('source_split','split')):
                raise ValueError('ROLLOUT_SPLIT_UNVERIFIED')
            e={k:field(row,path) for k,path in mapping['fields'].items()}
            if 'route_key' not in e:
                join=mapping['route_join']
                if set(join)-{'dataset','scene','instruction_id','episode_id'}:
                    raise ValueError('unsupported route join fields')
                if 'scene' not in join or not ({'instruction_id','episode_id'}&set(join)):
                    raise ValueError('route join requires scene and instruction/episode identity')
                values={k:field(row,v) for k,v in join.items()}
                values['scene']=Path(str(values['scene'])).stem
                matches=[r for r in routes if all(str(r.get(k))==str(v) for k,v in values.items())]
                if len(matches)!=1:raise ValueError('ambiguous/missing official route join')
                e['route_key']=route_key(matches[0])
            if e['route_key'] not in lookup:raise ValueError('not in official train route index')
            if task is not None:
                known=lookup[e['route_key']]
                if parts[0]!=known['dataset'] or Path(parts[3]).stem!=known['scene']:
                    raise ValueError('native trace route identity mismatch')
                if known['dataset']=='rxr' and parts[2]!='en-US':raise ValueError('native RxR trace is not en-US')
                if known['dataset']=='r2r' and parts[2] not in ('en', 'en-US'):
                    raise ValueError('native R2R trace language mismatch')
                # Dataset+scene identity alone is insufficient: distinct
                # instructions and episodes frequently share a Matterport scan.
                # Reject silent joins onto the wrong route even when the raw
                # event explicitly claims a train split.
                native_instruction = parts[5]
                official_instruction = str(known.get('instruction_id', ''))
                if native_instruction != '-' and native_instruction != official_instruction:
                    raise ValueError('NATIVE_TRACE_INSTRUCTION_MISMATCH')
                native_episode = parts[4]
                official_episode = known.get('episode_id')
                if official_episode is not None and str(official_episode) != native_episode:
                    raise ValueError('NATIVE_TRACE_EPISODE_MISMATCH')
                if native_instruction == '-' and official_episode is None:
                    raise ValueError('NATIVE_TRACE_UNVERIFIED_INSTRUCTION_AND_EPISODE')
                # When the original trace omits an instruction ID, a verified
                # episode join is the sole permitted fallback.
            e['call_id']=int(e['call_id']);e['source_split']='train'
            e['image_paths']=[str(training_path(Path(p) if Path(p).is_absolute() else source.parent/p)) for p in e['image_paths']]
            e['raw_provenance']={'file':str(source),'sha256':source_sha,'record':i}
            # No default target_source, target_text, replay_verified or success.
            accepted.append(e)
        except (KeyError,ValueError,TypeError,IndexError) as exc:
            rejected.append({'record':i,'reason':str(exc)})
    return accepted,rejected
