# 10 · Scanner 扫描去重

> 遍历源文件夹、按扩展名过滤、算指纹、与仓储比对，产出待处理清单。纯逻辑，注入接口。
> **依赖**：00、09。 **位置**：`pipeline/scanner.py`。 **详见** detailed-design §3.10。

## 子任务
- [ ] 指纹算法：`sha256(文件大小字节 + 头部 4MB)`
- [ ] `Scanner.scan(source_folders, extensions) -> list[ClipCandidate]`
- [ ] 扩展名白名单过滤（大小写不敏感）
- [ ] 调 `repository.exists_fingerprint` 跳过已入库

## 完成标准（DoD）
- [ ] 单测（临时目录造文件 + 内存仓储）：只挑白名单扩展名
- [ ] 单测：跳过已存在指纹
- [ ] 单测：相同内容不重复入列
