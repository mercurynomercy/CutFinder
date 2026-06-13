# 08 · LibraryWriter 库文件组织

> 把原文件**复制**到 `库/YYYY-MM-DD/A-roll|B-roll/`，保留时间，处理重名。**原文件只读。**
> **依赖**：00。 **接口**：`ports/library.py:LibraryWriter`。 **详见** detailed-design §3.8。

## 子任务
- [x] `adapters/fs_library.py:FsLibraryWriter.copy_into(src, date, roll) -> str`
- [x] `shutil.copy2` 保留 mtime/atime；目标目录按 `日期/类型` 自动创建
- [x] 重名 → 追加 `(1)`、`(2)`…，绝不覆盖
- [x] 复制后校验大小一致

## 完成标准（DoD）
- [x] 单测（临时目录真小文件）：原文件未被改动（mtime/内容不变）— `test_original_file_unchanged_content`, `test_original_file_unchanged_mtime`
- [x] 单测：目标路径符合 `YYYY-MM-DD/A-roll|B-roll/` — `test_copy_to_new_path`, `test_copy_b_roll`, `test_directories_created_auto`
- [x] 单测：重名不覆盖、自动加序号 — `test_first_conflict_appends_1`, `test_second_conflict_appends_2`, `test_existing_file_unchanged_after_conflict_copy`
- [x] 单测：复制后 mtime 保留、大小一致 — `test_copy_preserves_mtime`, `test_size_mismatch_raises_os_error`

## 测试
16 个单测全部通过：`tests/unit/test_fs_library.py`

## Fake
- `FakeLibraryWriter` — `tests/fakes/fake_library.py`，记录调用参数并返回确定性路径。
