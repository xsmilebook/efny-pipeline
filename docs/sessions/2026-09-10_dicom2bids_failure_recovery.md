# DICOM 转换失败恢复规则

根据批处理日志中集中出现的场图冲突、单序列转换失败、SST `bad` 列识别失败、重复
T1 和不完整 rest 等问题，调整 `dicom2bids_checked.m` 的选择与失败隔离规则。

同一扫描内仍以场图序列的最大 DICOM 文件数表示完整采集，并分别检查普通场图和
`_TASK` 场图是否形成平衡的 AP/PA 对。仅一类完整时，将该类场图关联到该扫描的全部
BOLD；两类都完整时，普通场图只关联 rest，`_TASK` 场图只关联任务态 BOLD。没有完整
AP/PA 对时省略场图并报告 warning，不再终止整名被试。

Prescan Normalize T1 在候选中先保留 DICOM 文件数最多者，再按采集时间选择最后一次。
rest 重扫优先选择最后一个 180-volume 候选；不存在 180-volume 候选时仍转换最后一次
可用采集，同时报告 warning。

`dcm2niix` 改为 `-i n`，避免再次过滤已经由脚本明确选择的 derived 或 2D 序列。
单序列转换失败只取消该序列并报告 warning；功能场图任一方向失败时成对取消，防止
输出不完整的 AP/PA 对。

事件 CSV 使用 `VariableNamingRule='preserve'` 保留原始标题。SST 的 `bad` 列在去除
首尾空白和可能的 BOM 后执行不区分大小写的唯一匹配，避免 MATLAB 自动修改其他列名
后出现无法识别 `bad` 的错误；匹配不到或存在多个候选时仍明确报错，避免错误生成试次
类型。

验证使用 MATLAB R2025a `checkcode` 解析修改后的脚本。仅返回一条已被源码抑制、且
分析器说明不再产生的历史消息 `MSNU`，未发现语法错误。完整 DICOM 批处理耗时较长，
本次未重新运行；正式验证入口仍为 `run_dicom2bids_checked`。
