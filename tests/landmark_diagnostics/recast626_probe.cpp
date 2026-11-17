#include "Recast.h"
#include <iostream>
int main() {
 rcContext ctx(false);
 for (int gap=59;gap<=61;++gap) {
  rcHeightfield* hf=rcAllocHeightfield();float lo[3]={0,0,0},hi[3]={1,4,1};
  if(!rcCreateHeightfield(&ctx,*hf,1,1,lo,hi,1.0f,0.025f)) return 2;
  if(!rcAddSpan(&ctx,*hf,0,0,0,1,RC_WALKABLE_AREA,0)) return 3;
  if(!rcAddSpan(&ctx,*hf,0,0,1+gap,2+gap,RC_NULL_AREA,0)) return 4;
  rcFilterWalkableLowHeightSpans(&ctx,60,*hf);
  std::cout<<gap<<" "<<int(hf->spans[0]->area)<<"\n";
  rcFreeHeightField(hf);
 }
}
