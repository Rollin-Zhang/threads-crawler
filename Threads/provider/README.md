# Threads Provider 模組（A 握手骨架）

此目錄僅建立骨架與說明，不含任何實作程式碼。

結構：
- adapters/（ingest、normalize）
- triage/（gate0、builder、batcher、client、fetcher、persist、schemas/）
- api/（app.py 展示與 dry-run）
- cli/（threads_tool.py）
- store/（candidates_sent.jsonl、pending.jsonl、triage_results.jsonl、dead_letter/）

參考文檔：`docs/triage/A-handshake-design.md`
