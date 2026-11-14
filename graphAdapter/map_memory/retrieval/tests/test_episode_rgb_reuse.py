"""Source pixels may be reused; revision bindings and file integrity are always checked."""
from contextlib import closing
import hashlib
from PIL import Image
import pytest
from graphAdapter.map_memory.storage.archive import IntegrityError,UnavailableMaterial
from graphAdapter.map_memory.storage.pages import EpisodeImageCache,FactMaterializer

def test_readers_share_only_verified_images_and_release_at_episode_end(tmp_path):
    cache=EpisodeImageCache(tmp_path,3*4*4,episode='first')
    def make(name,color):
        f=tmp_path/name
        Image.new('RGB',(4,4),color).save(f)
        data=f.read_bytes()
        return dict(path=f.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    a=make('a.png','blue');b=make('b.png','red')
    cache.bind(tmp_path,'first')
    for root,episode in [(tmp_path,'other'),(tmp_path/'other','first')]:
        with pytest.raises(IntegrityError):cache.bind(root,episode)
    with closing(FactMaterializer(tmp_path,{},image_cache=cache)) as first:
        image=first.image(a)
    assert not cache.closed and not image.flags.writeable and cache.decodes==1
    with closing(FactMaterializer(tmp_path,{},image_cache=cache)) as second:
        assert second.image(a) is image and cache.decodes==1
        meta=tmp_path/'meta.json';meta.write_bytes(b'{}')
        second.facts={'view':dict(rgb=a,host_view=a,meta=dict(path=meta.name,bytes=2,sha256=hashlib.sha256(b'{}').hexdigest()))}
        row=second.view('view',{},'pin')
        assert row['raw_rgb'] is image and row['host_view'] is image
        with pytest.raises(ValueError):row['raw_rgb'].setflags(write=True)
        with pytest.raises(TypeError):row['raw_rgb']=None
        assert tuple(second.image(b)[0,0])==(255,0,0)
        assert tuple(image[0,0])==(0,0,255)
        assert cache.image_bytes==48 and len(cache.images)==1
        second.image(a)
        assert cache.decodes==3
        f=tmp_path/'a.png';raw=f.read_bytes();f.write_bytes(bytes([raw[0]^1])+raw[1:])
        with pytest.raises(IntegrityError,match='checksum'):second.image(a)
        f.unlink()
        with pytest.raises(UnavailableMaterial):second.image(a)
    cache.close()
    assert cache.closed and cache.image_bytes==0 and not cache.images
    with pytest.raises(IntegrityError):cache.image(a)
