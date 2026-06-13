# 09 · CatalogRepository 仓储（SQLite）

> 所有 SQLite 读写的唯一入口；全文搜索用 FTS5。
> **依赖**：00。 **接口**：`ports/repository.py:CatalogRepository`。 **详见** detailed-design §3.9、§5。

## 子任务
- [ ] 建表 SQL + 初始化：`clips`、`tags`、`transcripts`、`jobs` + FTS5 虚拟表 `clips_fts`
- [ ] `adapters/sqlite_repo.py:SqliteRepository` 实现：
  - [ ] `exists_fingerprint` / `upsert_clip`（幂等）/ `get_clip`
  - [ ] `query_clips(filter)`（按 date/type/tag 过滤）
  - [ ] `search(q)`（FTS5 跨 summary/description/transcript）
  - [ ] `set_tags` / `correct_roll`（置 `roll_source='manual'`）
  - [ ] `update_analysis`（re-analyze：只更 auto 标签 + summary/description/transcript，保留 manual）
  - [ ] job CRUD：`create_job` / `update_job` / `get_job`

## 完成标准（DoD）
- [ ] 单测（`:memory:` 真 SQL）：CRUD、过滤、FTS 搜索命中
- [ ] 单测：`upsert_clip` 幂等（同指纹不重复）
- [ ] 单测：`correct_roll` 置 manual；`update_analysis` 保留 manual 标签/A-B、只刷新 auto
