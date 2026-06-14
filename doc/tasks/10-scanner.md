# 10 · Scanner 扫描去重

> 遍历源文件夹、按扩展名过滤、算指纹、与仓储比对，产出待处理清单。纯逻辑，注入接口。
> **依赖**：00、09。 **位置**：`pipeline/scanner.py`。 **详见** detailed-design §3.10。

## 子任务
- [x] 指纹算法：`sha256(文件大小字节 + 头部 4MB)`
- [x] `Scanner.scan(source_folders, extensions) -> list[ClipCandidate]`
- [x] 扩展名白名单过滤（大小写不敏感）
- [x] 调 `repository.exists_fingerprint` 跳过已入库

## 完成标准（DoD）
- [x] 单测（临时目录造文件 + 内存仓储）：只挑白名单扩展名
- [x] 单测：跳过已存在指纹
- [x] 单测：相同内容不重复入列

## 测试覆盖（27 tests, all passing）
- `_is_hidden`: root、正常路径、点文件、嵌套点目录（5 tests）
- `_compute_fingerprint`: 64-char hex、确定性、不同内容不同指纹、同内容相同指纹、文件大小差异、空文件（6 tests）
- 扩展名过滤: whitelist 白名单、大小写不敏感、默认包含 m4v、无匹配文件（4 tests）
- 仓库去重: 跳过已存在指纹、允许新指纹（2 tests）
- 内部去重: 同内容不重复入列、不同内容都保留（2 tests）
- 隐藏文件过滤: 跳过点文件、跳过隐藏目录内文件（2 tests）
- 边界情况: 不存在的文件夹静默跳过、空目录无候选、多文件夹扫描、不可读文件跳过、返回 ClipCandidate 实例、候选对象字段正确（8 tests）
