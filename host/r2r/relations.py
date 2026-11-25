"""Source-only retrieval cues. Matches are not semantic findings or cut decisions."""
import re
FACET_PATTERNS={
 'conditional_routes':r'\bif\b[^.!?]{0,180}(?:[.!?]\s*)?\botherwise\b',
 'required_return':r'\b(?:return|backtrack|retrace)\b|\bback\s+to\s+(?:the\s+)?(?:same|original)\b',
 'stair_turn':r'\b(?:stairs?|staircase)\b[^.!?]{0,70}\b(?:turn|right|left)\b',
 'landmark_placement':r'\b(?:stop|wait|stand)\b[^.!?]{0,80}\b(?:near|by|beside|behind|front|at)\b',
 'arrival_trigger':r'\b(?:once|when|until)\b[^.!?]{0,80}\b(?:reach|get|at|see)\b',
 'pass_then_placement':r'\b(?:past|pass|passing)\b[^.!?]{0,120}(?:\.|,)\s*(?:then\s+)?(?:stop|wait)\b',
 'expected_view':r'\b(?:you (?:will |should |can )?(?:see|face)|you are facing|there (?:is|are))\b',
 'door_identity':r'\b(?:door|doorway)\b[^.!?]{0,70}\b(?:with|above|beside|across|other side|far|right|left)\b',
 'hall_end_entry':r'\b(?:end of (?:the )?(?:hall|hallway|corridor)|hallway end)\b',
 'final_approach':r'\b(?:toward|towards|approach)\b',
 'hall_transit':r'\b(?:walk|go|continue|follow)\b[^.!?]{0,80}\b(?:hall|hallway|corridor)\b',
 'ordered_turns':r'\b(?:turn|take|make)\b[^.!?]{0,25}\b(?:left|right)\b',
 'room_entry':r'\b(?:enter|into|inside)\b[^.!?]{0,60}\b(?:room|bedroom|bathroom|hall|kitchen)\b',
 'pass_then_turn':r'\b(?:past|pass|passing)\b[^.!?]{0,90}\b(?:turn|take)\b',
 'doorway_stop':r'\b(?:stop|wait|stand)\b[^.!?]{0,65}\b(?:door|doorway|entrance)\b',
 'open_door_attribute':r'\bopen\s+(?:(?:glass|double|sliding|arched)\s+)?doors?\b',
 'transit_before_exit_stop':r'\b(?:stop|wait)\b[^.!?]{0,80}\bbefore\b[^.!?]{0,45}\b(?:exit|outside|leav\w*)\b',
 'door_count_origin':r'\b(?:exit|leave|exiting|leaving|out of)\b[^.!?]{0,90}\b(?:first|second|third)\s+(?:open )?door\b',
 'ordinal_door':r'\b(?:first|second|third|fourth|last|1st|2nd|3rd)\s+(?:open )?(?:door|doorway)\b',
 'ordered_landmarks':r'\b(?:past|pass|passing)\b[^.!?]{0,100}\b(?:past|pass|passing)\b',
 'hall_until_bedroom':r'\b(?:hall|hallway|corridor)\b[^.!?]{0,100}\buntil\b',
 'preparatory_turn_ascent':r'\bturn\b[^.!?]{0,60}\b(?:up|climb|ascend)\b',
 'modifier_attachment':r'\b(?:passing|past)\b[^.!?]{0,80}',
 'ordinal_placement':r'\b(?:first|second|third|fourth)\s+(?:tile|step|landing)\b',
 'bounded_ascent_refinement':r'\b(?:one|two|three|four|\d+)\s+(?:steps?|stairs?)\b',
 'ordered_crossings':r'\b(?:exit|through|out of)\b[^.!?]{0,120}\b(?:exit|through|out of)\b',
 'explicit_arrival':r'\b(?:arrived|arrival|reach|reaching|get to)\b',
 'stair_wait':r'\b(?:stop|wait)\b[^.!?]{0,55}\b(?:stairs?|staircase|top|bottom)\b',
 'behind_target':r'\b(?:behind|back of)\b',
 'center_door_selection':r'\b(?:center|middle)\s+door\b',
 'object_relative_room':r'\b(?:room|door)\b[^.!?]{0,45}\b(?:left|right) of (?:the )?(?:stairs?|staircase)\b',
 'ordinal_room':r'\b(?:first|second|third|fourth)\s+room\b',
 'uncertain_name':r"\b(?:unclear|unknown|not sure|cannot tell|can't tell)\b",
 'stair_destination':r'\b(?:continue|proceed|go|walk)\b[^.!?]{0,55}\b(?:stairs?|staircase)\b',
 'hall_entry':r'\b(?:enter|into)\s+(?:the |a )?(?:hall|hallway|corridor)\b',
 'turnaround_entry':r'\bturn\s+around\b',
 'turn_after_landmark':r'\bturn\b[^.!?]{0,35}\bafter\b',
 'prohibited_entry':r"\b(?:do not|don't|never)\s+(?:enter|go|walk)\b",
 'final_facing':r'\b(?:stop|wait|stand)\b[^.!?]{0,70}\bfacing\b',
 'maintained_frame':r'\b(?:keep|while|with)\b[^.!?]{0,80}\b(?:left|right|facing)\b',
 'initial_frame':r'\b(?:with|facing)\b[^.!?]{0,80}\b(?:back|behind)\b',
 'turn_until_frame':r'\bturn\b[^.!?]{0,35}\buntil\b',
 'surface_motion':r'\b(?:walk(?:ing)?|go(?:ing)?|move|moving|continue|proceed|head)\b(?:(?!\b(?:stop|wait|stand|onto|from|turn|enter|exit|leave|with|to)\b)[^.!?,;]){0,65}\b(?:on|along)\s+(?:the |a )?(?:[a-z]+\s+){0,2}(?:carpet|rug|runner|path|walkway|floor)\b|\b(?:follow|following)\s+(?:the |a )?(?:[a-z]+\s+){0,2}(?:carpet|rug|runner|path|walkway)\b|(?:^|[.!?;]\s*)\b(?:on|along)\s+(?:the |a )?(?:[a-z]+\s+){0,2}(?:carpet|rug|runner|path|walkway|floor)\s*,\s*(?:walk|go|move|continue|proceed|head)\b',
 'window_side':r'\b(?:left|right)\b[^.!?]{0,30}\bwindows?\b',
}

def applicability(item, query_facets):
    """Source-only eligibility for specialist teaching, before ranking.

    Ordinary lessons have no gate. A missing specialist relation is a normal
    exclusion, not a technical failure or a request to alter the source.
    """
    required = item.get('required_query_facets', [])
    if (not isinstance(required, list) or any(not isinstance(f,str) or f not in FACET_PATTERNS for f in required)
            or len(set(required)) != len(required)):
        raise ValueError('Invalid specialist applicability metadata')
    return not required or bool(set(required) & set(query_facets))


def facet_signals(text):
    if not isinstance(text,str):raise TypeError('Source must be a string')
    out = {}
    for name, pattern in FACET_PATTERNS.items():
        spans = []
        for match in re.finditer(pattern, text, re.I):
            if name == 'required_return' and re.search(r"(?:do not|don't|never)\s+(?:go\s+)?$", text[:match.start()], re.I):
                continue  # a prohibition is not an instruction to revisit
            spans.append(dict(start=match.start(), end=match.end(), quote=match.group()))
        if spans:
            out[name] = spans
    return out


def route_family(provenance, split):
    """Host-only exclusion identity, never used to infer a route or model facts."""
    if not isinstance(provenance,dict) or split in (None,'','unspecified'):return None
    scene=provenance.get('scene_id') or provenance.get('scan_id')
    path=provenance.get('trajectory_id') or provenance.get('path_id')
    if scene is None or path is None:return None
    scene=str(scene).replace('\\','/').rsplit('/',1)[-1].removesuffix('.glb')
    if not scene:return None
    return '|'.join(('R2R',str(split),scene,str(path)))
