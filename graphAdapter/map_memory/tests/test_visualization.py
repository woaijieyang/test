"""Height-slice and read-only offline visualization contracts,CPU."""
from pathlib import Path
import json,re
import numpy as np
from graphAdapter.map_memory.geometry.core import TSDFTile
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
from graphAdapter.map_memory.visualization import slice_points,render_episode
from test_storage import EP,archive,graph

def test_G12_two_heights_same_horizontal_cell_are_not_flattened_and_render_is_readonly(tmp_path):
    store=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(store,1)
        tile=TSDFTile("tile_0_0_0",np.array([[0.,2.],[0.,2.],[0.,2.]]),.25,np.eye(4),
                      base_position_L=np.zeros(3),near_m=0,far_m=10)
        tile.free_count[1,1,1]=1
        tile.surface_count[1,1,5]=1
        record=store.save_tile(tile)
        g=graph([1]);g["geometry_state"]=dict(origin_G=[0,0,0],voxel_size=.25)
        g["views"][next(iter(g["views"]))]["T_G_base"]=np.eye(4).tolist()
        g["views"][next(iter(g["views"]))]["geometry_status"]="available"
        g["tiles"]={tile.tile_id:dict(pose_map_version=0,record=record)}
        store.publish(g,{"pose_map_version":0},{"capture_seq":1,"event_seq":10})
        before=(store.root/"CURRENT.json").read_bytes()
        reader=load_episode(store.root)
        low,lowstate,info=slice_points(reader,".25")
        high,highstate,info2=slice_points(reader,"1.25")
        assert len(low)==len(high)==1 and lowstate.tolist()==[1]and highstate.tolist()==[2]
        np.testing.assert_array_equal(low[:,[0,2]],high[:,[0,2]])
        assert low[0,1]==.25 and high[0,1]==1.25 and info["floor_id"]is None
        reader.close()
        out=tmp_path/"visual"
        report=render_episode(store.root,out=out,height_slice=".25")
        assert report["height_slice"]["floor_id"]is None
        assert (out/"geometry_bev.png").stat().st_size>1000
        page=(out/"index.html").read_text()
        assert "floor_id" in page and "估计世界" in page
        payload=json.loads(re.search(r"const data=(.*?);document.querySelector",page,re.S).group(1))
        assert all((out/v["rgb"]).resolve().is_file()for v in payload["views"]if v["rgb"]is not None)
        assert before==(store.root/"CURRENT.json").read_bytes()
        load=load_episode(store.root);load.verify();load.close()
    finally:store.close()
