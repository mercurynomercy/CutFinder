# 08 · LibraryWriter 库文件组织

> 把原文件**复制**到 `库/YYYY-MM-DD/A-roll|B-roll/`，保留时间，处理重名。**原文件只读。**
> **依赖**：00。 **接口**：`ports/library.py:LibraryWriter`。 **详见** detailed-design §3.8。

## 子任务
- [ ] `adapters/fs_library.py:FsLibraryWriter.copy_into(src, date, roll) -> Path`
- [ ] `shutil.copy2` 保留 mtime/atime；目标目录按 `日期/类型` 自动创建
- [ ] 重名 → 追加 ` (1)`、` (2)`…，绝不覆盖
- [ ] 复制后校验大小一致

## 完成标准（DoD）
- [ ] 单测（临时目录真小文件）：原文件未被改动（mtime/内容不变）
- [ ] 单测：目标路径符合 `YYYY-MM-DD/A-roll|B-roll/`
- [ ] 单测：重名不覆盖、自动加序号
- [ ] 单测：复制后 mtime 保留、大小一致
