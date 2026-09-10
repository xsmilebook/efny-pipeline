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

`dcm2niix` 保持使用 `-i y`；已确认该参数不会过滤本队列选中的 Prescan Normalize T1
和 DWI B0 序列。单序列转换失败只取消该序列并报告 warning；功能场图任一方向失败时
成对取消，防止输出不完整的 AP/PA 对。

事件 CSV 使用 `VariableNamingRule='preserve'` 保留原始标题。SST 的 `bad` 列在去除
首尾空白和可能的 BOM 后执行不区分大小写的唯一匹配，避免 MATLAB 自动修改其他列名
后出现无法识别 `bad` 的错误；匹配不到或存在多个候选时仍明确报错，避免错误生成试次
类型。

后续批处理发现，保留原始标题后仍直接访问 `MRI_Signal_s_started` 等 MATLAB 自动修改
形式会导致回归：PsychoPy 原始组件字段通常使用 `MRI_Signal_s.started`、
`Trial_fix.started` 和 `key_resp.rt` 等点号标题。现已将所有共同字段及任务特异字段统一
通过显式表头映射解析；接受文档化的点号形式及旧导出的下划线形式，并在计算前一次性
验证任务所需列。缺列或歧义错误会报告所选 CSV 路径和全部实际表头。事件文件选择、
表头验证、事件计算或写出失败均只跳过对应任务并报告 warning，不再使已成功转换的影像
被标记为整名被试失败。

验证使用 MATLAB R2025a `checkcode` 解析修改后的脚本。仅返回一条已被源码抑制、且
分析器说明不再产生的历史消息 `MSNU`，未发现语法错误。完整 DICOM 批处理耗时较长，
本次未重新运行；正式验证入口仍为 `run_dicom2bids_checked`。

针对 PsychoPy 表头修正，另以包含上述六个点号组件字段、`bad` 和
`Trial_loop_list` 的合成 CSV 完成 MATLAB R2025a 冒烟测试；`preserve` 导入后的原始
字段名和动态字段访问均符合预期。测试文件位于系统临时目录并已自动清理。
