from graphAdapter.map_memory.retrieval.protocol import native_slot_indices
from graphAdapter.map_memory.retrieval.tests.test_host_input_compiler import native_sampler
import pytest
from PIL import Image

@pytest.mark.parametrize('budget',[1,2,4,8,12])
def test_slot_ids_agree_with_original_host_pixel_sampling(budget):
    sample=native_sampler()
    for n in sorted({1,max(1,budget-1),budget,budget+1,20,34,501}):
        images=[Image.new('RGB',(1,1),(i%255+1,i//255,0)) for i in range(n)]
        pixels=[x.getpixel((0,0)) for x in sample(images,num_frames=budget,width=1,height=1)]
        indices=native_slot_indices(n,budget)
        assert pixels==[(0,0,0) if i is None else images[i].getpixel((0,0)) for i in indices]
        assert len(indices)==budget and indices[-1]==n-1



@pytest.mark.parametrize("budget",[1,2,4,8,12])
def test_selective_copy_has_native_pixels_and_independent_ownership(budget):
    from graphAdapter.map_memory.retrieval.protocol import sample_native_rgb
    for n in (1,7,8,12,57,501):
        images=[Image.new("RGB",(3,5),(i%251+1,i//251,9))for i in range(n)]
        got=sample_native_rgb(images,num_frames=budget,width=3,height=5)
        expected=native_sampler()(images,num_frames=budget,width=3,height=5)
        assert [(p.mode,p.size,p.tobytes())for p in got]==[(p.mode,p.size,p.tobytes())for p in expected]
        got[-1].putpixel((0,0),(0,0,0))
        assert images[-1].getpixel((0,0))!=got[-1].getpixel((0,0))
