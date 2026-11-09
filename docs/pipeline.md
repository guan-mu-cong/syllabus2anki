# 管线详解（pipeline.md）

> 从官方大纲 PDF 到 Anki 可用的重卡牌组：9 个阶段、config 驱动、全阶段断点续跑。
> 所有阶段均可离线复跑（网络仅 02/03/04 首次抓取需要）。

## 阶段总览

| # | 脚本 | 输入 | 输出 | 网络 | 断点续跑 |
|---|------|------|------|------|----------|
| 01 | `01_extract_wordlist.py` | 官方大纲 PDF | 词表 json（word/star/page/variants） | 否 | 否（秒级） |
| 02 | `02_fetch_dict.py` | 词表 | `yd_cache/<word>.json` 词典缓存 | **是** | 天然（缓存即断点） |
| 03 | `03_audio.py` | 词表 + 词典缓存 | `audio32/*.mp3` + `audio_map2.json` | **是**（缺才下） | 天然（文件即断点） |
| 04 | `04_translate.py` | 例句缺口 | `translations.json` 译文缓存 | **是**（LLM） | 天然（缓存即断点） |
| 05 | `05_build_cards.py` | 缓存全家桶 | `cards.json`（21+ 字段/卡） | 否 | 否（分钟级） |
| 05b | `05b_attribute.py` | cards.json | `attributor_audit.jsonl`（义项归因） | LLM 可选 | 是（jsonl 已有词跳过） |
| 05c | `05c_finalize.py` | cards + audit | `cards_final.json`（加粗烘焙、删核心义） | 否 | 否（秒级） |
| 06 | `06_write_anki.py` | cards_final + audio32 | Anki 实卡（AnkiConnect） | 否（本机） | 是（written_log / media done_log） |
| 07 | `07_audit.py` | cards_final / 实库 | QA 报告（G1-G4 闸 + 媒体对账） | 否 | — |

数据流：

```
PDF ─01→ 词表 ─02→ 词典缓存 ─03→ 音频+map ─┐
                     │                      ├─05→ cards.json ─05b→ audit.jsonl ─05c→ cards_final.json
              真题语料/词频索引(自备,可选) ──┘                                        │
                                                            06 ←──────────────────┘
                                                             ↓ (AnkiConnect)
                                                          Anki 牌组 ←─07 审计(实库模式)
```

## 环境变量（S2A_*）

vendor 模块（`pipeline/lib/`）与生产代码逐字节同行为，唯一区别是路径/凭据全部
经环境变量注入——wrapper 会按 config 自动设置，手工直跑 lib 时才需要关心：

| 变量 | 含义 | 默认 |
|------|------|------|
| `S2A_DATA_DIR` | 工作数据目录（所有缓存与中间文件的家） | lib 文件所在目录 |
| `S2A_ENTRIES` | 词条文件名（data_dir 内），`entries`/`words`/裸列表三种 schema 都认 | `entries_7619.json` |
| `S2A_CARDS` | 05b/05c 的输入 cards json | `$DATA_DIR/cards.json` |
| `S2A_AUDIT` | 归因台账 jsonl | `$DATA_DIR/attributor_audit.jsonl` |
| `S2A_CARDS_FINAL_OUT` | 05c 输出 | `$DATA_DIR/cards_final.json` |
| `S2A_AUDIO_MAP_OUT` | 03 输出 map | `$DATA_DIR/audio_map2.json` |
| `S2A_NO_LLM` | `1` = 05b 纯规则模式（完全离线） | 关 |
| `S2A_LLM_API_KEY` / `S2A_LLM_URL` / `S2A_LLM_MODELS` | 05b/04 的 LLM（OpenAI 兼容） | key 空 = 拒绝调用 |

**密钥纪律**：任何 key 只从环境变量或仓库外的文件路径读取（config 里存的是
*变量名* 或 *仓库外绝对路径*），永不写入代码/配置/仓库。

## 各阶段要点

### 01 提取
PyMuPDF 文本层 + 逐页校验 + 人工核实的 fixups（详见 `docs/pitfalls.md`）。
自检词机制防「静默丢词」——末页单词条页（如 `★zoom`）曾被整页吞掉。

### 02 词典缓存
默认 provider = 有道公开词典接口（jsonapi，个人学习用途缓存，见 compliance）。
`check` 模式完全离线，报覆盖率；`fetch` 模式线程池 + 礼貌延时，缓存文件即断点。
换 provider：写一个 `fetch_<name>(word, cfg) -> raw text` 注册进 `PROVIDERS`。

### 03 音频
按词典缓存里的 speech URL 下载 → ffmpeg 压成 32kbps 单声道（约 5KB/条）→
产出 `word → {uk, us}` 文件名 map（05 建卡时烘焙成 `[sound:]` 引用）。
`check` 模式离线报覆盖率。已存在且 >800B 的文件跳过 = 天然断点。

### 04 译文
扫描 05 会渲染的全部例句（真题 + 高质量），凡无中文且缓存未命中的送 LLM 翻译；
缓存 key = 清洗后的英文原句（与建卡端 `_zh_for` 完全一致，保证命中率）。
`dry-run` 模式离线报缺口。

### 05 建卡（核心）
`lib/build_v3.py + build_all.py`：义项清洗（语域标签保留、脏义项仅按精确标记剔除）、
核心义 = 最常用义（有 COCA 分布时以其校准）、价值分档排序键（★ > 真题 > 短常用 > 派生，
档内按 wordfreq zipf 降序）、真题例句挑选、柯林斯块、搭配/同根词渲染。
辅助数据文件（plan/corpus/hbs/engra…）全部**可选**——缺了就空载降级（新词自动走
`synthetic_plan` 现场解析路径）。

### 05b 归因（v5 卡面扩展）
决定每条义项里**哪个中文词加粗**（`<b class="xt">`）：有真题有效例句 → LLM 终判
（高置信才落笔，宁缺毋滥）；无例句的★词频层 → 规则默认粗首条；真题层例句无效 →
诚实留白。台账 jsonl 追加式，天然断点。`llm.enabled: false` = 纯规则全离线。

### 05c 烘焙
把台账加粗进 `常用义项`、删 `核心义` 字段（v5 规格：核心义活在加粗里）。
幂等（已有同词加粗跳过），确定性（同输入 → 字节级同输出）。

### 06 写入 Anki
`init / sync-template / push-media / push-notes / forget / stats` 六个子命令。
批量 addNotes 遇 duplicate 整批异常 → 自动逐条重投（已存在的跳过）；
written_log / media done_log 双断点。`--dry-run` 全离线出载荷样例。

### 07 审计
- **file 模式**：G1 实体残留（硬闸）/ G2 结构（搭配、编号、记忆块、必填字段）/
  G3 覆盖率+重复（硬闸）/ G4 语义（核心义 vs COCA、例句支撑、长度分布——仅 v4 输入）。
- **anki 模式**：只读扫实库 + `[sound:]` 引用与 collection.media 目录**双向对账**
  （引用缺失 = 播放坏，硬闸；孤儿 = 占空间）。
- 退出码：0 干净 / 1 硬闸失败 / 2 仅提示。

## 回归证据（对 7805 词生产库，2026-11-09/10）

| 验证 | 结果 |
|------|------|
| 05 建卡 vs 生产 cards.json | 7805 卡 × 26 字段 **字节级一致**（3m44s） |
| 05b 规则路径 vs 生产台账 | 3986/3986 词 strategy+picks **全同**（含 ★zoom） |
| 05c 烘焙 vs 生产 cards_final.json | **sha256 一致**（30,980,692 B） |
| 06 载荷 vs Anki 实卡 | 随机 20 词 × 20 字段 **逐字节一致** |
| 07 anki 模式实库 | 3501 卡 G1 残留 0；媒体对账 7002 引用 = 7002 文件，缺失 0 孤儿 0 |
| 02 缓存覆盖 | 7805/7805 = 100%（离线 check） |
| 04 译文缓存 | 命中 4765 句，缺口 4（生产既有，如实报告） |
| mini20 合成示例 | 6 阶段全离线通过 + 全部不变量断言 |

注：03 重建 map 与历史生产 map 存在 45 处大小写 + 3 处重音/空格词的**文件名变体**
差异（磁盘上两种命名的文件都存在，实卡引用不受影响）——历史多脚本命名习惯所致，
新库单次跑 03 天然自洽。详见 `docs/pitfalls.md` 下游章节。

## 目录约定

```
syllabus2anki/
├─ pipeline/            # 01-07 阶段脚本 + lib/（vendor 的生产引擎）
├─ assets/templates/    # v5 卡面模板（front/back/css，自研设计，MIT）
├─ examples/mini20/     # 20 个合成词的离线全链路示例
├─ docs/                # 本文档 + pitfalls + compliance
├─ config.example.yaml  # 全量配置模板（可提交）
└─ config.local.yaml    # 本机路径与凭据指针（gitignore，永不提交）
```
