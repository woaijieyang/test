"""Human-readable, curated lesson annotations over verified public training text.

Rows below are authored teaching judgments, not official subtask annotations.
Coverage tuples: source quote, stage index, candidate quote, requirement.
Stage tuples: executable text, target quote, completion quote, ending kind,
             condition quotes, explanation of inherited/initial entry.
Mutations replace exactly one quoted span; they are synthetic negative candidates.
"""

ARCHIVE_URL = 'https://storage.googleapis.com/rxr-data/rxr_train_guide.jsonl.gz'
ARCHIVE_SHA256 = 'b28b374b6e3203874f8bf65293df102b698efd51109e7e81a0e86fe3e3f780f2'

LESSONS = [
{
'id': 'correction', 'instruction_id': 564, 'scan': 'ULsKaCPVFJR', 'path_id': 244,
'record_sha256': 'bac97c0b2cb1bfe28ad450ff475d78c407e8077fcc5abd44d2ea14a662454527',
'source': "You begin in what appears to be a walk-in closet area. You'll notice a mirror to your right, and a doorway to your left, but, you're going to go straight through the one you begin facing. Should be entering a bedroom with a lot of white and blue decor. You will veer slightly left... Or, sorry, slightly right, moving towards the backless couch. Move towards the right side of it. And, once you are on that far side of the backless couch, you're done.",
'pattern': 'local_correction',
'lesson': 'The correction changes only the veer direction. Preserve the earlier doorway traversal, bedroom identity and couch-side endpoint. The next stage can inherit the established bedroom without another entry command.',
'anti': 'Do not execute the superseded left veer or delete the closet-to-bedroom route. Do not make the described mirror a visit target.',
'stages': [
("You begin in what appears to be a walk-in closet area. You'll notice a mirror to your right, and a doorway to your left, but, you're going to go straight through the one you begin facing. You should be entering a bedroom with a lot of white and blue decor.", 'a bedroom with a lot of white and blue decor', 'entering a bedroom with a lot of white and blue decor', 'explicit_event', ['mirror to your right', 'a doorway to your left', 'the one you begin facing'], 'The source supplies the initial closet area and facing doorway.'),
("Veer slightly right, moving towards the backless couch. Move towards the right side of it. Once you are on that far side of the backless couch, you're done.", 'that far side of the backless couch', 'Once you are on that far side of the backless couch', 'explicit_event', ['slightly right', 'the right side of it'], 'Inherit the bedroom reached by the preceding doorway traversal; no additional entry action is required.')],
'coverage': [
('You begin in what appears to be a walk-in closet area.',0,'You begin in what appears to be a walk-in closet area.','Preserve the described starting area without inventing a pose.'),
("You'll notice a mirror to your right, and a doorway to your left, but, you're going to go straight through the one you begin facing.",0,"You'll notice a mirror to your right, and a doorway to your left, but, you're going to go straight through the one you begin facing.",'Preserve side references but choose the doorway initially faced.'),
('Should be entering a bedroom with a lot of white and blue decor.',0,'entering a bedroom with a lot of white and blue decor','Complete the traversal into the identified bedroom.'),
('You will veer slightly left... Or, sorry, slightly right, moving towards the backless couch.',1,'Veer slightly right, moving towards the backless couch.','Apply the local LEFT-to-RIGHT correction while retaining the couch approach.'),
('Move towards the right side of it.',1,'Move towards the right side of it.','Retain the right side of the same backless couch.'),
("And, once you are on that far side of the backless couch, you're done.",1,"Once you are on that far side of the backless couch, you're done.",'Preserve the final far-side placement, not merely a couch mention.')],
'mutation': {'stage':1,'old':'Veer slightly right','new':'Veer slightly left','requirement':3,'code':'WRONG_REFERENCE_FRAME','problem':'The candidate executes the explicitly superseded left veer.','consequence':'It initiates the couch approach in the opposite direction after the bedroom entry.'}
},
{
'id':'repetition','instruction_id':17649,'scan':'B6ByNegPMKs','path_id':6483,
'record_sha256':'b26e468cb266594803065b12eb433c68532966e55b1ecba4870a21e92922bed3',
'source':"Look around, you're currently in a white room with a black window pane to your right. Turn left, and walk straight down that hallway. Walk straight down that hallway, until you see the red exit sign in front of you. Turn right, and enter the nearest room opened in the left. Pass through that beige door, and enter that empty room. Once you're at the center of that empty white room, you have reached your final destination.",
'pattern':'oral_repetition',
'lesson':'The second hallway clause supplies the until endpoint for the same straight traversal. Preserve the visual trigger; it is not an arrival at the sign. The later right turn and left-side room selection remain as authored.',
'anti':'Do not introduce another hallway traversal from repeated oral wording or silently change the source turn/door geometry.',
'stages':[
("Look around, you're currently in a white room with a black window pane to your right. Turn left, and walk straight down that hallway until you see the red exit sign in front of you.",'the red exit sign in front of you','until you see the red exit sign in front of you','explicit_event',['black window pane to your right','Turn left'],'The source establishes the starting white room and window reference.'),
("Turn right, and enter the nearest room opened in the left. Pass through that beige door, and enter that empty room. Once you're at the center of that empty white room, you have reached your final destination.",'the center of that empty white room',"Once you're at the center of that empty white room",'explicit_event',['Turn right','nearest room opened in the left','that beige door'],'Inherit the state at which the exit sign has become visible; no arrival at the sign is asserted.')],
'coverage':[
("Look around, you're currently in a white room with a black window pane to your right.",0,"Look around, you're currently in a white room with a black window pane to your right.",'Keep the initial look and right-side window reference.'),
('Turn left, and walk straight down that hallway. Walk straight down that hallway, until you see the red exit sign in front of you.',0,'Turn left, and walk straight down that hallway until you see the red exit sign in front of you.','One left-turn/hallway traversal is refined by the sign-visibility trigger, not an extra lap.'),
('Turn right, and enter the nearest room opened in the left.',1,'Turn right, and enter the nearest room opened in the left.','Preserve the subsequent right turn and nearest left-side room selection.'),
('Pass through that beige door, and enter that empty room.',1,'Pass through that beige door, and enter that empty room.','Retain actual beige-door traversal and empty-room entry.'),
("Once you're at the center of that empty white room, you have reached your final destination.",1,"Once you're at the center of that empty white room, you have reached your final destination.",'Complete at the room center, not at its entrance.')],
'mutation':{'stage':0,'old':'walk straight down that hallway until','new':'walk straight down that hallway again until','requirement':1,'code':'UNSUPPORTED_ADDITION','problem':'The candidate adds again to a continuation whose second source clause refines its endpoint.','consequence':'It can command a further hallway traversal not required by the source.'}
},
{
'id':'paired-choice','instruction_id':745,'scan':'ZMojNkEp431','path_id':320,
'record_sha256':'65b471fcc045d9cf52fac585aa5a8632c466e6ac1cafd7beed187a6f2ab46b78',
'source':"You begin facing a white couch with green pillows. Turn to your left and you're going to notice two sets of stairs with a section of wall between them. You're going to walk to the leftmost set of stairs, and then you're going to walk own them. Rather once you're standing at the top of the stairs you're done.",
'pattern':'paired_spatial_choice',
'lesson':'Leftmost selects a member of the described pair, not a third staircase to the left of both. The final rather clause refines/corrects the same stair movement to completion at the top; do not execute a descent first.',
'anti':'Do not infer a new staircase outside the pair or a full descent before returning to the top.',
'stages':[
("You begin facing a white couch with green pillows. Turn to your left and you'll notice two sets of stairs with a section of wall between them. Walk to the leftmost set of stairs. Once you're standing at the top of the stairs, you're done.",'the top of the stairs',"Once you're standing at the top of the stairs",'explicit_event',['Turn to your left','two sets of stairs with a section of wall between them','leftmost set of stairs'],'The initial facing relation is supplied by the source.')],
'coverage':[
('You begin facing a white couch with green pillows.',0,'You begin facing a white couch with green pillows.','Preserve initial facing and the couch attributes.'),
("Turn to your left and you're going to notice two sets of stairs with a section of wall between them.",0,"Turn to your left and you'll notice two sets of stairs with a section of wall between them.",'Preserve the turn and the observed pair with intervening wall.'),
("You're going to walk to the leftmost set of stairs",0,'Walk to the leftmost set of stairs.','Select the leftmost member of the two sets, not a location left of both.'),
("and then you're going to walk own them. Rather once you're standing at the top of the stairs you're done.",0,"Once you're standing at the top of the stairs, you're done.",'Apply the explicit final correction at the top rather than carrying out an additional descent.')],
'mutation':{'stage':0,'old':'Walk to the leftmost set of stairs.','new':'Walk to the set of stairs to the left of both sets.','requirement':2,'code':'WRONG_RELATION','problem':'The candidate changes selection within a pair to a position outside the pair.','consequence':'It can direct the agent to a different staircase not identified by the source.'}
},
{
'id':'ordinal-origin','instruction_id':28,'scan':'7y3sRwLe3Va','path_id':12,
'record_sha256':'2f8de293769d35ddf22604ae69392ef2db67c2ffd7bf05126ca8c56a9409bc8f',
'source':"You're starting in a closet, facing empty shelves and a drawer unit. To your left, is the door to exit, and just beyond that, is another door that leads into a hallway. Walk through the closet door and that second door toward the hallway. When you get in the threshold between the bedroom and the hallway with the stairs, you're finished.",
'pattern':'ordinal_origin',
'lesson':'The second door is the door beyond the closet exit, not a fresh second-door count after reaching the hall. Keep the traversal and threshold refinement together.',
'anti':'Do not reset the count or replace the bedroom/hallway threshold by arrival inside the hallway.',
'stages':[
("You're starting in a closet, facing empty shelves and a drawer unit. To your left, is the door to exit, and just beyond that, is another door that leads into a hallway. Walk through the closet door and that second door toward the hallway. When you get in the threshold between the bedroom and the hallway with the stairs, you're finished.",'the threshold between the bedroom and the hallway with the stairs','When you get in the threshold between the bedroom and the hallway with the stairs','explicit_event',['To your left','just beyond that','that second door'],'Start in the source-described closet facing shelves and drawer unit.')],
'coverage':[
("You're starting in a closet, facing empty shelves and a drawer unit.",0,"You're starting in a closet, facing empty shelves and a drawer unit.",'Preserve the closet start and initial facing.'),
('To your left, is the door to exit, and just beyond that, is another door that leads into a hallway.',0,'To your left, is the door to exit, and just beyond that, is another door that leads into a hallway.','Identify the closet exit first and the hall door beyond it.'),
('Walk through the closet door and that second door toward the hallway.',0,'Walk through the closet door and that second door toward the hallway.','Traverse both identified doors without resetting the count.'),
("When you get in the threshold between the bedroom and the hallway with the stairs, you're finished.",0,"When you get in the threshold between the bedroom and the hallway with the stairs, you're finished.",'Finish at the bedroom/hallway threshold, not after another doorway selection.')],
'mutation':{'stage':0,'old':'that second door toward the hallway','new':'the second door you find after entering the hallway','requirement':2,'code':'COUNT_SCOPE_DRIFT','problem':'The candidate restarts the second-door count after hallway entry.','consequence':'It skips the specifically identified door beyond the closet exit and selects a later door.'}
},
{
'id':'bounded-placement','instruction_id':60,'scan':'S9hNv5qa7GM','path_id':24,
'record_sha256':'fd9af8f8eda8e4b27b83746444bda12fc3122dd2f2d1c9fcc2721fe80dabb411',
'source':"You begin facing a wall, turn to your left, take a step towards the front of the bed, using the door that's to the left of the dresser, exit the bedroom, you will enter a hallway, once you've entered the hallway, look immediate to your left, there will be an opening, take a step towards the opening, once you're standing in the hallway, outside of the opening facing the living room with the red couches, you are done.",
'pattern':'terminal_refinement',
'lesson':'Bedroom exit establishes the next stage entry. Preserve the bounded step toward the opening and the final outside-opening position facing the living room; the living room is not an entry target.',
'anti':'Do not strengthen the one-step approach into entering the living room or create a separate redundant stop stage.',
'stages':[
("You begin facing a wall, turn to your left, take a step towards the front of the bed, using the door that's to the left of the dresser, exit the bedroom and enter the hallway.",'the hallway','exit the bedroom and enter the hallway','explicit_event',['turn to your left','a step towards the front of the bed',"the door that's to the left of the dresser"],'The initial facing-wall state is supplied by the source.'),
("Look immediately to your left; there will be an opening. Take a step towards the opening. Once you're standing in the hallway, outside of the opening facing the living room with the red couches, you are done.",'outside of the opening facing the living room with the red couches',"Once you're standing in the hallway, outside of the opening facing the living room with the red couches",'explicit_event',['Look immediately to your left','a step towards the opening','outside of the opening'],'Inherit the hallway reached by the preceding exit; do not repeat that exit command.')],
'coverage':[
('You begin facing a wall, turn to your left, take a step towards the front of the bed',0,'You begin facing a wall, turn to your left, take a step towards the front of the bed','Retain initial facing, left turn and a bounded step toward the bed front.'),
("using the door that's to the left of the dresser, exit the bedroom, you will enter a hallway",0,"using the door that's to the left of the dresser, exit the bedroom and enter the hallway",'Use the dresser-left door to exit into the hallway.'),
("once you've entered the hallway, look immediate to your left, there will be an opening",1,'Look immediately to your left; there will be an opening.','Only after hallway entry look left for the opening.'),
('take a step towards the opening',1,'Take a step towards the opening.','Preserve one step toward the opening, not a full visit to the next room.'),
("once you're standing in the hallway, outside of the opening facing the living room with the red couches, you are done.",1,"Once you're standing in the hallway, outside of the opening facing the living room with the red couches, you are done.",'Finish in the hallway outside the opening, facing the red-couch living room.')],
'mutation':{'stage':1,'old':'outside of the opening facing the living room with the red couches','new':'inside the living room with the red couches','requirement':4,'code':'WRONG_TARGET','problem':'The candidate moves the final placement from outside the opening to inside the living room.','consequence':'It requires an unsupported room entry and loses the source-facing configuration.'}
},
{
'id':'return-history','instruction_id':45476,'scan':'V2XKFyX4ASd','path_id':4184,
'record_sha256':'32d555a74feab100ceefd750a3bd710c62a7f353fd8b923d2888c79b03f7d7e4',
'source':"Looking at the picnic table inside, walk directly at the right hand corner of the picnic table, closest to the fridge. Once you get there, turn back around and head, facing the TV, couch and chairs, to the left there is an open doorway, walk back through that open doorway, in the area of which you came. You're now in a bedroom, walk to the foot of the bed, between the TV and the bed, walk past the Jacuzzi tub into the open doorway straight ahead. In the open doorway, the toilet on your left, turn to the right. You'll see a shower, walk into the shower. Standing in the shower, you've reached your final destination.",
'pattern':'return_identity',
'lesson':'The picnic-table corner is an actual intermediate objective before the return. Preserve the turn back, the previously traversed open doorway and the later shower entry; a repeated region does not erase intervening events.',
'anti':'Do not substitute another doorway for the return or shortcut from the initial location to the final bedroom route.',
'stages':[
('Looking at the picnic table inside, walk directly at the right hand corner of the picnic table, closest to the fridge.','the right hand corner of the picnic table, closest to the fridge','walk directly at the right hand corner of the picnic table, closest to the fridge','explicit_event',['right hand corner','closest to the fridge'],'Start looking at the inside picnic table as described.'),
("Once you get there, turn back around and head, facing the TV, couch and chairs, to the left there is an open doorway. Walk back through that open doorway, in the area of which you came. You're now in a bedroom.",'the area of which you came','Walk back through that open doorway','explicit_event',['Once you get there','facing the TV, couch and chairs','to the left','back through that open doorway'],'Inherit the completed picnic-table corner objective. The source Once you get there binds the turn back.'),
("Walk to the foot of the bed, between the TV and the bed, walk past the Jacuzzi tub into the open doorway straight ahead. In the open doorway, the toilet on your left, turn to the right. You'll see a shower, walk into the shower. Standing in the shower, you've reached your final destination.",'Standing in the shower','Standing in the shower','explicit_event',['between the TV and the bed','past the Jacuzzi tub','straight ahead','the toilet on your left','turn to the right'],'Inherit the bedroom established by the return; preserve all subsequent route events.')],
'coverage':[
('Looking at the picnic table inside, walk directly at the right hand corner of the picnic table, closest to the fridge.',0,'Looking at the picnic table inside, walk directly at the right hand corner of the picnic table, closest to the fridge.','First reach the table corner closest to the fridge.'),
('Once you get there, turn back around and head, facing the TV, couch and chairs, to the left there is an open doorway',1,'Once you get there, turn back around and head, facing the TV, couch and chairs, to the left there is an open doorway','Turn back only after the corner objective and retain the left-door viewpoint.'),
('walk back through that open doorway, in the area of which you came.',1,'Walk back through that open doorway, in the area of which you came.','Return through the identified doorway to the prior area, not a new doorway.'),
("You're now in a bedroom",1,"You're now in a bedroom.",'The return establishes the bedroom as the next entry state.'),
('walk to the foot of the bed, between the TV and the bed, walk past the Jacuzzi tub into the open doorway straight ahead.',2,'Walk to the foot of the bed, between the TV and the bed, walk past the Jacuzzi tub into the open doorway straight ahead.','Preserve bed-foot positioning and the Jacuzzi-to-doorway traversal.'),
('In the open doorway, the toilet on your left, turn to the right.',2,'In the open doorway, the toilet on your left, turn to the right.','Turn right at the doorway with the toilet on the left.'),
("You'll see a shower, walk into the shower. Standing in the shower, you've reached your final destination.",2,"You'll see a shower, walk into the shower. Standing in the shower, you've reached your final destination.",'Actually enter the shower and finish standing in it.')],
'mutation':{'stage':1,'old':'Walk back through that open doorway','new':'Walk through another open doorway','requirement':2,'code':'WRONG_TARGET','problem':'The candidate replaces the identified return doorway with another doorway.','consequence':'It loses route-history identity even if both routes happen to lead to a bedroom.'}
},
{
'id':'conditional-viewpoint','instruction_id':644,'scan':'8WUmhLawc2A','path_id':278,
'record_sha256':'128a5834b9fd520dc3437496bdb30b747e945af473569bfae6ec27b1b40b3702',
'source':"You're standing in the corner of a dining room, facing a wooden table with 7 chairs, 8 chairs. If you look to the right, you'll see there's an arch that leads into a living room. Walk towards that arch and if you look, while you standing below the arch if you look left you'll see the living room and a fire place, and a wooden cabinet on the left side. Walk towards that wooden cabinet on the left side. And once you're standing right in front of the wooden cabinet inside the living room and looking at a blue and orange painting next to the fireplace you're done.",
'pattern':'conditional_viewpoint',
'lesson':'Conditional looking identifies the arch and then the cabinet without creating alternative routes. The final cabinet-front position and painting gaze are both required. Preserve uncertain chair-count wording rather than sharpening it.',
'anti':'Do not create an extra visit to a reference object, drop the final gaze, or interpret seven/eight chairs as alternative navigation branches.',
'stages':[
("You're standing in the corner of a dining room, facing a wooden table with 7 chairs, 8 chairs. If you look to the right, you'll see there's an arch that leads into a living room. Walk towards that arch until you are standing below it.",'below it','until you are standing below it','explicit_event',["If you look to the right",'7 chairs, 8 chairs'],'The source provides the dining-room corner and table-facing state.'),
("While standing below the arch, if you look left you'll see the living room and a fire place, and a wooden cabinet on the left side. Walk towards that wooden cabinet on the left side. Once you're standing right in front of the wooden cabinet inside the living room and looking at a blue and orange painting next to the fireplace you're done.",'right in front of the wooden cabinet inside the living room',"Once you're standing right in front of the wooden cabinet inside the living room and looking at a blue and orange painting next to the fireplace",'explicit_event',["if you look left you'll see",'on the left side','looking at a blue and orange painting next to the fireplace'],'Below-arch context comes from the preceding supported completion and the original while clause.')],
'coverage':[
("You're standing in the corner of a dining room, facing a wooden table with 7 chairs, 8 chairs.",0,"You're standing in the corner of a dining room, facing a wooden table with 7 chairs, 8 chairs.",'Preserve the initial position, facing and non-sharpened chair description.'),
("If you look to the right, you'll see there's an arch that leads into a living room.",0,"If you look to the right, you'll see there's an arch that leads into a living room.",'Use the conditional right-looking observation to identify the arch without inventing a branch.'),
('Walk towards that arch and if you look, while you standing below the arch',0,'Walk towards that arch until you are standing below it.','Bind the later below-arch state to the same arch approach.'),
("if you look left you'll see the living room and a fire place, and a wooden cabinet on the left side.",1,"if you look left you'll see the living room and a fire place, and a wooden cabinet on the left side.",'Preserve the below-arch conditional left observation and cabinet identity.'),
('Walk towards that wooden cabinet on the left side.',1,'Walk towards that wooden cabinet on the left side.','Approach the identified left cabinet rather than the fireplace.'),
("And once you're standing right in front of the wooden cabinet inside the living room and looking at a blue and orange painting next to the fireplace you're done.",1,"Once you're standing right in front of the wooden cabinet inside the living room and looking at a blue and orange painting next to the fireplace you're done.",'Preserve final cabinet-front position and gaze at the identified painting.')],
'mutation':{'stage':0,'old':"If you look to the right, you'll see there's an arch that leads into a living room.",'new':'Turn right and walk into the living room.','requirement':1,'code':'UNSUPPORTED_ADDITION','problem':'The candidate converts an identifying conditional observation into immediate room entry before the arch approach.','consequence':'It prescribes an extra entry and changes the source event order.'}
},
{
'id':'late-description','instruction_id':942,'scan':'e9zR4mvMWw7','path_id':407,
'record_sha256':'fe738a4c31dc6035fad094a5f67b5c8cd44ae93a06947496adfe61a5e12d66c2',
'source':"You're currently looking into a mirror in the bedroom. Turn around, and face right. Take a step forward to the entrance of this blue bedroom. Take a step forward to the middle of the hallway. Turn slightly to the right. Go down the grey staircase. Once you're at the bottom of the grey staircase, take one large step forward to the entrance leading outside. It has two black doors open on each side. Now, take a large step forward in front of you, hopping over the brown mat, onto the grey pavement outside of the house. Once the brown mat is directly behind you, outside of the house, you're done.",
'pattern':'late_target_description',
'lesson':'Bind the two black doors to the outside entrance, keep the one large step and the mat-crossing as prescribed, and finish outside with the mat directly behind. Do not turn the entrance description into an extra door visit.',
'anti':'Do not drop either identifying door or substitute a generic outside goal for the final mat-relative position.',
'stages':[
("You're currently looking into a mirror in the bedroom. Turn around, and face right. Take a step forward to the entrance of this blue bedroom. Take a step forward to the middle of the hallway. Turn slightly to the right. Go down the grey staircase to its bottom.",'its bottom','Go down the grey staircase to its bottom','explicit_event',['Turn around, and face right','a step forward to the entrance','a step forward to the middle of the hallway','Turn slightly to the right'],'Start looking into the bedroom mirror. The following once-clause supplies the staircase-bottom completion.'),
("From the bottom of the grey staircase, take one large step forward to the entrance leading outside, which has two black doors open on each side. Now, take a large step forward in front of you, hopping over the brown mat, onto the grey pavement outside of the house. Once the brown mat is directly behind you, outside of the house, you're done.",'the grey pavement outside of the house',"Once the brown mat is directly behind you, outside of the house",'explicit_event',['one large step forward','two black doors open on each side','hopping over the brown mat','directly behind you'],'The staircase bottom anchors the source-prescribed large step and outside entrance choice.')],
'coverage':[
("You're currently looking into a mirror in the bedroom. Turn around, and face right.",0,"You're currently looking into a mirror in the bedroom. Turn around, and face right.",'Preserve initial mirror context and both orientation actions.'),
('Take a step forward to the entrance of this blue bedroom. Take a step forward to the middle of the hallway.',0,'Take a step forward to the entrance of this blue bedroom. Take a step forward to the middle of the hallway.','Retain the two bounded movements and their distinct reference positions.'),
("Turn slightly to the right. Go down the grey staircase. Once you're at the bottom of the grey staircase",0,'Turn slightly to the right. Go down the grey staircase to its bottom.','Bind the later bottom-of-staircase state to the same descent.'),
('take one large step forward to the entrance leading outside. It has two black doors open on each side.',1,'take one large step forward to the entrance leading outside, which has two black doors open on each side.','Bind the two-black-door description to the entrance before selection, retaining the large step.'),
('Now, take a large step forward in front of you, hopping over the brown mat, onto the grey pavement outside of the house.',1,'Now, take a large step forward in front of you, hopping over the brown mat, onto the grey pavement outside of the house.','Preserve the second large step over the mat onto the outside pavement.'),
("Once the brown mat is directly behind you, outside of the house, you're done.",1,"Once the brown mat is directly behind you, outside of the house, you're done.",'Finish outside with the mat directly behind the agent.')],
'mutation':{'stage':1,'old':'two black doors open on each side','new':'one black door on the left','requirement':3,'code':'WRONG_TARGET','problem':'The candidate changes the identifying pair of black doors to one left-hand door.','consequence':'It can select a different exit while appearing to preserve a generic outside destination.'}
}
]
