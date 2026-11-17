#include "Recast.h"
#include <iostream>
int main() {
 rcContext ctx(false);
 for (int drop: {0,12,20}) for (int gap=59;gap<=61;++gap) {
  rcHeightfield* hf=rcAllocHeightfield();float lo[3]={0,0,0},hi[3]={1,4,1};
  if(!rcCreateHeightfield(&ctx,*hf,3,3,lo,hi,0.05f,0.025f))return 2;
  for (int z=0;z<3;++z) for (int x=0;x<3;++x) {
   int floor=(x==2&&z==1)?21-drop:21;
   if(!rcAddSpan(&ctx,*hf,x,z,0,floor,RC_WALKABLE_AREA,0))return 3;
   if(!rcAddSpan(&ctx,*hf,x,z,21+gap,22+gap,RC_NULL_AREA,0))return 4;
  }
  rcFilterLedgeSpans(&ctx,60,12,*hf);
  rcFilterWalkableLowHeightSpans(&ctx,60,*hf);
  std::cout<<drop<<" "<<gap<<" "<<int(hf->spans[4]->area)<<"\n";
  rcFreeHeightField(hf);
 }
}
