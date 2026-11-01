# 结果比较 / Result Comparison

> 只比较数据集、split、role、language和episode manifest一致的实验。

| Run ID | Stage | Version | Dataset/Split | Episodes | SR | SPL | nDTW | sDTW | NE | Oracle SR | Timeout rate |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20261031-230245-case2-hamlet-abc-20261031-v2-r2r | hamlet-abc | aw4-seed10 | r2r/val_unseen | 1839 | 0.651441 | 0.566248 | 0.652729 |  | 3.972517 | 0.755846 |  |
| 20261031-230245-case2-hamlet-abc-20261031-v2-rxr | hamlet-abc | aw4-seed10 | rxr/val_unseen | 1223 | 0.674571 | 0.558815 | 0.672403 |  | 4.346312 | 0.756337 |  |
