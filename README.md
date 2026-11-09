# syllabus2anki

> **EN** — Turn an official exam-syllabus word list (PDF) into a full-featured
> Anki vocabulary deck: extraction with per-page validation, dictionary/audio/
> translation caching providers, a 21-field "heavy card" renderer (core-sense
> calibration, value-tier ordering, exam-example picking), LLM-assisted sense
> attribution with an honest rules-only fallback, AnkiConnect batch writing
> with resume, and a multi-gate QA auditor that also reconciles media
> references against your collection. Config-driven, resumable at every stage,
> regression-verified byte-identical against a 7,805-word production deck.
> **Code and methodology only** — dictionary content, audio and exam text are
> fetched locally by you and never redistributed (see `docs/compliance.md`).

从官方考试大纲 PDF 到 Anki 重卡牌组的全流程管线。为 CET-6（大学英语六级）7805 词
生产环境打造，代码与数据完全解耦：换一份大纲 PDF + 一份 config，就能为任何考试
词表铸一套同规格的牌组。

## 它解决什么问题

市售词书牌组要么词表来路不明、要么卡面信息稀薄、要么音频残缺。本项目把
「词表提取 → 词典/音频/译文缓存 → 21 字段重卡渲染 → 义项归因加粗 → 写入 Anki →
多闸审计」整条链变成可复跑、可断点、可回归验证的工程：

- **提取可靠**：逐页校验 + 自检词机制，专治 PDF 文本层的折行/全角/括号变体等
  七类坑（`docs/pitfalls.md` 全部记录在案，含一个吞掉末页单词条的真实缺陷案例）
- **卡面重而不乱**：核心义=最常用义（COCA 分布校准）、价值分档排序
  （★大纲词 > 真题词 > 短常用词 > 派生词，档内按词频降序）、真题例句优先、
  义项级加粗归因（LLM 终判 + 规则兜底，宁缺毋滥不硬凑）
- **工程可证**：全阶段断点续跑；对生产库回归 = 建卡字节级一致、规则归因
  3986/3986 全同、烘焙 sha256 一致、实卡抽样 20/20 一致、媒体对账零缺失
- **合规清楚**：仓库只有代码/模板/合成示例；词典内容、音频、真题文本由你
  本机抓取自用，永不随仓分发（`docs/compliance.md` 有逐项矩阵）

## 快速开始（离线 demo，5 分钟）

```bash
pip install -r requirements.txt
cd examples/mini20
python run_demo.py        # 20 个合成词跑通 6 个阶段 + 全部断言
```

不需要网络、不需要 Anki、不含任何真实词典内容。

## 生产流程

```bash
cp config.example.yaml config.local.yaml   # 填本机路径；此文件已被 gitignore
# 01 提取词表（需要本地官方 PDF）
python pipeline/01_extract_wordlist.py --config config.local.yaml
# 02-04 缓存三件套（需要网络；02 词典 / 03 音频+ffmpeg / 04 译文+LLM key）
python pipeline/02_fetch_dict.py --config config.local.yaml check   # 先看覆盖率
python pipeline/02_fetch_dict.py --config config.local.yaml fetch
python pipeline/03_audio.py     --config config.local.yaml run
python pipeline/04_translate.py --config config.local.yaml run
# 05 建卡三阶段（离线）
python pipeline/05_build_cards.py --config config.local.yaml
python pipeline/05b_attribute.py --config config.local.yaml --all   # llm.enabled:false=纯规则
python pipeline/05c_finalize.py  --config config.local.yaml
# 06 写入 Anki（本机 Anki + AnkiConnect 运行中）
python pipeline/06_write_anki.py --config config.local.yaml init
python pipeline/06_write_anki.py --config config.local.yaml push-media
python pipeline/06_write_anki.py --config config.local.yaml push-notes --dry-run  # 先看载荷
python pipeline/06_write_anki.py --config config.local.yaml push-notes
# 07 审计（file + anki 双模式）
python pipeline/07_audit.py --config config.local.yaml file
python pipeline/07_audit.py --config config.local.yaml anki --media-dir "<collection.media 路径>"
```

每个阶段的输入输出、S2A_* 环境变量、config 全量参考：`docs/pipeline.md`。

## 目录

```
pipeline/            阶段脚本 01-07（05b/05c 为 v5 卡面扩展）
pipeline/lib/        vendor 的生产引擎（建卡/归因/烘焙/音频，与生产回归一致）
assets/templates/    v5 卡面模板（front/back/css）
examples/mini20/     离线合成示例（20 词全链路）
docs/                pipeline / pitfalls / compliance
config.example.yaml  配置模板（可提交）
```

## 密钥纪律

API key（LLM）与 AnkiConnect key 只从**环境变量**或**仓库外文件**读取，
config 里只出现变量名/路径。提交前脱敏扫描：

```bash
grep -rniE "api[_-]?key\s*=\s*[A-Za-z0-9]|sk-[A-Za-z0-9]|C:\\\\Users|/home/[a-z]" \
  --include="*.py" --include="*.yaml" --include="*.md" . \
  | grep -v "os.environ" && echo "!! 有残留" || echo "clean"
```

## 状态

- [x] M1 词表提取 + 回归（7805 词/★1263，抓到并修复生产缺陷 ★zoom）
- [x] M2 建卡引擎 vendor + 回归（字节级一致）
- [x] M3 I/O 模块（词典/音频/译文/写入/审计）+ 生产回归
- [x] M4 文档 + mini20 示例
- [ ] M5 终审发布（脱敏扫描通过 → 公开）

## License

MIT（代码与模板）。抓取内容的版权归各自权利人——见 `docs/compliance.md`。
