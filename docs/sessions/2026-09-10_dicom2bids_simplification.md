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

批处理入口 `run_dicom2bids_checked.m` 改为无参数 MATLAB 脚本，在文件顶部固定
dcm2niix、NIfTI、BIDS、原始数据、被试清单路径及并行数。被试级 `parfor` 上限
为 4；每个被试使用独立 `try/catch`，单个被试失败仅发出 warning，不中断其他
被试。原有清单去空、重复源目录和重复 BIDS 标签预检查均已删除。

删除独立的 `bids_subject_label.m`，将 ID 解析直接放入单被试转换函数。原始目录
`THU_YYYYMMDD_ID_姓名...` 转为 `sub-THUYYYYMMDDXXXX`：三位 ID 补一个前导零，
四位 ID 保持不变，数字 ID 后的姓名及其他字符串不写入 BIDS。

修正辅助目录导致被试提前失败的问题。`inspectSeries` 现在先按目录名分类，
`LOCALIZER*`、`PHOENIXZIPREPORT*`、DWI 派生目录以及 FM、PM、PR、NBACK_V 等
不支持序列在读取 DICOM 前直接跳过。只有实际参与 BIDS 分配的序列才要求存在
DICOM 文件；Prescan Normalize 私有字段也只为 T1 读取。
