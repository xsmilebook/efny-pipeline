# DICOM2BIDS 转换脚本精简

根据实际转换需求，删除 `dicom2bids_checked.m` 中不参与序列选择或 BIDS 分配的
统计逻辑：主函数不再返回序列清单，不再生成 `conversion_manifest.tsv`，并移除
仅服务于该清单的 `decision`、`scanRelative` 字段和赋值循环。

同时保留文件数、采集时间、Prescan Normalize、同 scan fmap 配对、同 scan
DWI/B0 配对、BIDS 目标唯一性和转换后 fieldmap 参数检查。这些字段和检查直接
参与最终文件选择或防止错误分配，不属于统计输出。

使用 THU_604 的真实 fieldmap DICOM 进行冒烟测试：较短 AP 被排除，完整 AP/PA
成功转换为两个 fmap NIfTI 和 JSON；未生成 manifest，也未生成空的 func、anat、
dwi 目录。
