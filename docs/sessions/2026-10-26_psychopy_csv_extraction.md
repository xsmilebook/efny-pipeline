# PsychoPy 原始 CSV 筛选与提取入口

## 请求与环境

- 用户要求只提取原始 PsychoPy CSV，目标文件选择与当前项目转换规则一致。
- 用户确认 `Z:\xuhaoshu\PSYCH_tlr` 为输出根目录，输入参考 DICOM-to-BIDS 入口。
- 项目根目录：`D:\projects\efny-pipeline`；本地 Windows，MATLAB R2025a。
- 开发起点 commit：`20b1249`，开始时工作区干净。本次代码和文档在提交前处于未提交状态；
  最终版本由本会话提交记录定位。本次未切换至集群，不涉及 Slurm 作业。

## 实现

- 新增 `scripts/neuroimaging/extract_psychopy_csv.m` 和
  `scripts/neuroimaging/run_extract_psychopy_csv.m`。
- 入口输入沿用 `run_dicom2bids_checked.m` 的 `D:\Raw_trans`；输出为
  `Z:\xuhaoshu\PSYCH_tlr`。默认处理输入根目录下全部符合现有命名的 THU 被试目录，
  也支持以第三个参数传入 DICOM 转换使用的源被试名单。
- 仅复制 SST、n-back、switch 各自选中的原始 CSV，保持源被试目录名、`PSYCH` 层级、
  原文件名和内容；不复制 log 或 psydat，不修改源数据或转换 events。
- 任务文件名识别、原始 `readtable` 行数优先及文件名时间戳破同分沿用现有局部函数；
  新入口只增加候选行数返回值及明确的歧义错误标识，不改选择结果。
- 先完成全批次选择，再复制。歧义及缺失 PSYCH 目录直接报错；缺失任务给 warning 并记录。
  同名结果允许再次复制；若目标被试已有不在当前选择中的 CSV，则在复制前报错，保留旧文件。
- 输出根目录的 `selection_log.json` 保留候选、行数、选择路径、缺失任务和 MATLAB 版本。
  不计算文件内容哈希，不改动 `data/`、`outputs/` 或现有转换器，不新增依赖。
- README 同步用法；详细规则与边界见 `docs/psychopy_csv_extraction.md`。

## 现有毫秒行为的核实

MATLAB R2025a 实测：当前正则虽然整体匹配 `.001` 等毫秒后缀，但 `tokens` 结果只有
日期、小时、分钟和秒四项；嵌套于非捕获分组内的毫秒 token 没有返回。
因此两个现有转换器的实际排序精度为秒。同秒、不同毫秒、且最大行数相同的文件仍报歧义。
为遵守与当前实现一致的要求，新入口保留该行为，并添加专门测试和文档说明；未修改旧脚本。

## 验证

- 三个新增 MATLAB 文件（提取函数、运行入口、测试）通过 `checkcode(..., '-id')`，无诊断。
- 运行 `results = runtests('tests/test_extract_psychopy_csv.m'); assertSuccess(results);`，
  7 项测试全部通过。覆盖原始行数优先、时间破同分、无时间戳的唯一最长文件、任务标记、
  CSV 内容不变、同秒毫秒差异与缺时间戳导致的歧义、缺失任务、旧文件保护、重复运行及名单。
- 首轮测试暴露了测试夹具写 `.log` 时需指定文本格式、断言缺省错误标识与测试预期不同；
  修正测试夹具并为新入口的歧义和旧目标 CSV 错误增加标识后验证通过。
- 使用用户给出的已有示例目录作为只读输入，对单被试 `THU_20260728_1006_LWY` 做实际文件
  复制冒烟验证，目标为系统临时目录，通过临时名单限定一名被试。复制三份 CSV，逐文件
  `fileread` 内容完全一致；SST、n-back、switch 的原始数据行数分别为 183、52、148。
  这些是原始 CSV 行数，不是有效 trial 数或 events 数，也没有据此判断实验完整性。
- 合成测试与实际文件冒烟均使用系统临时目录，并通过清理代码移除。既有示例输出未写入。
- `git diff --check` 通过。

当前 `D:\Raw_trans` 和 `D:\BIDS_transfer\raw\sublist.txt` 在本机不可见。
因此本次完成脚本实现及上述验证，未执行从 RAW 到 `PSYCH_tlr` 的正式全量提取。
正式运行前需确认或修改入口输入路径，按实际范围选择全目录或显式名单。
