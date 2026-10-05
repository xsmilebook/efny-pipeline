# BIDS 验证与容器代理设置

用户明确要求 fMRIPrep 跳过 BIDS 验证，运行失败后再检查输入，并保留参考代理以备需要。

- 阅读 ARCHITECTURE，并对照 data_driven_EF 参考脚本中的代理设置。
- fMRIPrep 增加 `--skip-bids-validation`，不另加预验证步骤。
- fMRIPrep／XCP-D 移除清除代理的逻辑，恢复 `http://10.11.100.5:3128`；
  导出宿主 HTTP／HTTPS／FTP／ALL 大小写代理变量及对应 `SINGULARITYENV_*`，显式传入容器。
- 同步 AGENTS、README、集群手册、影像流程与参数对照文档，记录两项已与参考一致。
- 验证使用既有 14 项合成测试，并在模拟容器中检查 16 个宿主／容器代理变量，检查跳过验证参数。
  两份修改的 Bash 脚本通过语法检查，临时测试产物在结束后清理。
- 未连接集群、测试真实代理连通性或运行真实容器；未改动正式数据与结果。
