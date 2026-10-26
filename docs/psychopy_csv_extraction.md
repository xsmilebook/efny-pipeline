# PsychoPy 原始 CSV 提取

## 用途与路径

`scripts/neuroimaging/extract_psychopy_csv.m` 只筛选、复制原始 CSV，不转换影像或 events，
不删除 trial，不修改 CSV 内容、文件名或源数据。只复制 CSV，不复制 `.log`、`.psydat`。

入口 `scripts/neuroimaging/run_extract_psychopy_csv.m` 的输入沿用
`run_dicom2bids_checked.m`：`D:\Raw_trans`。输出设为 `Z:\xuhaoshu\PSYCH_tlr`。
运行前应按当前机器实际挂载情况修改入口顶部的两个路径；不自动寻找备用路径。

输出示例：

```text
Z:\xuhaoshu\PSYCH_tlr\
├── selection_log.json
└── THU_20260728_1006_LWY\
    └── PSYCH\
        ├── THU_20260728_1006_LWY_SST_0702_2026-07-28_13h47.09.864.csv
        ├── THU_20260728_1006_LWY_nback_2026-07-28_13h43.02.514.csv
        └── THU_20260728_1006_LWY_switch_2026-07-28_13h31.43.409.csv
```

## 调用

在 MATLAB 中运行上述入口，或显式传入路径：

```matlab
addpath('D:\projects\efny-pipeline\scripts\neuroimaging');
extract_psychopy_csv('D:\Raw_trans', 'Z:\xuhaoshu\PSYCH_tlr');
```

不传第三个参数时，枚举输入根目录直属、符合现有 THU 命名规则的被试目录：
`THU_八位日期_三至四位编号`，其后可带姓名等后缀，分隔符支持下划线或连字符。
不递归搜索其他目录。

若需严格沿用 DICOM 转换的名单，传入第三个参数：

```matlab
extract_psychopy_csv('D:\Raw_trans', 'Z:\xuhaoshu\PSYCH_tlr', ...
    'D:\BIDS_transfer\raw\sublist.txt');
```

名单每行一个源被试文件夹名。空行忽略，重复被试名报错。提取不需要 `dcm2niix`，
也不要求读取 `MRIdata`；原始根目录下存在对应的 `被试/PSYCH` 即可。

## 与当前项目一致的选择规则

1. 只查看每个被试 `PSYCH` 直属的 `*.csv`。
2. 使用现有正则 `(?<=_)(sst|nback|switch)(?=_)`，大小写不敏感。
   文件名必须识别出唯一一种支持的任务；未识别或同时包含不同任务标记的文件不参与选择。
3. 每个任务只有一个候选文件时直接选中，不额外要求时间戳或 events 字段。
4. 多个候选文件通过 `readtable(..., 'VariableNamingRule', 'preserve')` 读取，
   以 `height` 得到的原始数据行数最多者为优先。
5. 最大行数并列时，仅在并列候选中比较文件名时间戳，格式为
   `YYYY-MM-DD_HHhMM.SS`，文件名可带三位毫秒，选最新且唯一的一份。
   当前 MATLAB 正则的 token 结果不包含嵌套毫秒分组，实际比较精度为秒；
   同秒但毫秒不同的文件仍视为并列。新入口保留该行为，未改动原有转换器。
6. 并列候选缺少可识别时间戳，或最新时间戳仍重复时，停止并报告错误，不猜测。

上述任务识别、行数和时间戳规则直接沿用两个 BIDS 转换器的局部函数。
“行数最多”统计发生在任何 trial 过滤之前，不代表实验完整或行为 QC 合格。
提取过程不进行有效 trial 数、正确率或 events 时间轴检查，不与 BOLD 采集时间匹配。
每个行为任务独立选择，与 PsychoPy-only 转换器的任务范围一致；完整 DICOM 转换器则
只为保留的任务 BOLD 生成 events。

## 输出与错误处理

- 全部被试选择完成后才复制；某任务选择歧义不会先复制其他任务。
- 缺少 `PSYCH` 目录直接报错。某支持任务没有匹配 CSV 时发出 warning，记录为
  `missing_task_csv`，其余任务继续；全批次没有选中文件时报错。
- 可以重复复制同名选中文件。若目标被试 `PSYCH` 已有不在本次选择中的 CSV，复制前
  报错，需指定新的输出根目录。脚本不会删除这些旧文件。
- 未在本次范围中的被试和目标目录内的非 CSV 文件保持原状。
- 每次成功复制后写入根级 `selection_log.json`，记录当前调用的输入、输出、名单路径、
  本机时间、MATLAB 版本及每个被试任务的候选路径、候选行数、选中文件、目标路径和状态。
  仅单候选时行数留空，因当前规则无需读取该文件；候选行数与候选路径按相同顺序对应。
  该日志是来源明细，不作为被试汇总表，也不计算文件内容哈希。
- 运行期间复制或写日志失败会直接报错，可能留下部分已复制文件；没有成功结束的日志
  不能作为完成依据。

## 验证与运行记录

科学定向测试位于 `tests/test_extract_psychopy_csv.m`：

```matlab
results = runtests('tests/test_extract_psychopy_csv.m');
assertSuccess(results);
```

测试覆盖原始行数优先、时间破同分、同秒不同毫秒仍报歧义、无时间戳的唯一最长候选、任务标记识别、
复制内容不变、时间歧义在复制前失败、缺失任务记录、旧文件保护、重复运行和显式名单。
使用系统临时目录，测试结束清理。批量提取前先用少量被试确认输入与输出挂载位置。
正式运行另记录代码 commit、工作区状态、调用命令和范围；当前实现没有执行全量提取。
