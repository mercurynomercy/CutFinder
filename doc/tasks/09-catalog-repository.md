# 09 · CatalogRepository 仓储（SQLite）

> 所有 SQLite 读写的唯一入口；全文搜索用 FTS5。
> **依赖**：00。 **接口**：`ports/repository.py:CatalogRepository`。 **详见** detailed-design §3.9、§5。

## 子任务
- [x] 建表 SQL + 初始化：`clips`、`tags`、`transcripts`、`jobs` + FTS5 虚拟表 `clips_fts`
- [x] `adapters/sqlite_repo.py:SqliteRepository` 实现：
  - [x] `exists_fingerprint` / `upsert_clip`（幂等）/ `get_clip`
  - [x] `query_clips(filter)`（按 date/type/tag 过滤）
  - [x] `search(q)`（FTS5 trigram tokenizer，跨 summary/description/transcript；短查询回退 LIKE）
  - [x] `set_tags` / `correct_roll`（置 `roll_source='manual'`）
  - [x] `update_analysis`（re-analyze：只更 auto 标签 + summary/description/transcript，保留 manual）
  - [x] job CRUD：`create_job` / `update_job` / `get_job`

## 完成标准（DoD）
- [x] 单测（`:memory:` 真 SQL）：CRUD、过滤、FTS 搜索命中 — `tests/unit/test_sqlite_repo.py`，35/35 通过
- [x] 单测：`upsert_clip` 幂等（同指纹不重复）
- [x] 单测：`correct_roll` 置 manual；`update_analysis` 保留 manual 标签/A-B、只刷新 auto

## Fake
- `FakeRepository` — `tests/fakes/fake_repository.py`，记录调用参数并返回确定性值。

## 备注
- FTS5 使用 `tokenize=trigram` tokenizer，原生支持 CJK 多字匹配；短查询（<3 字符）回退到 LIKE + transcripts JOIN。
- FTS5 同步通过三个 IF NOT EXISTS trigger（insert/update/delete）+ `save_transcript` 中的 `_sync_fts_transcript()` 实现。
