# flight-price-pdf-skill

[中文](README.md) | [English](README.en.md)

本地 Codex skill，可查询任意出发地和目的地的 Trip.com 实时机票，并自动生成 PDF。支持单程、往返、玩几天或住几晚，原始 JSON 只落盘，不打印到终端或对话。

## 功能

- `flight-price` CLI 驱动 Playwright 无头 Chromium
- **v0.4 新增 `run_flight_pdf.py` 端到端一键脚本**：多出发地 × 日期窗口一次跑完（扫描 → 超时自动重试一次 → 汇总 → 中文 HTML → PDF），终端只打印不超过 3 行摘要；PDF 走 Playwright 渲染，**不需要 reportlab**，Python 3.9 即可运行
- Agent 协作协议：长扫描以后台任务启动后立即结束回合，脚本完成后自动产出 PDF，全程零原始 JSON 回传
- 默认生成 PDF；`flight_report.py` 可选生成 XLSX 或 DOCX
- 支持任意出发地/目的地、单程/往返、多日期、指定日期对、航司和转机筛选
- 理解“玩 8 天”与“住 8 晚”的区别：前者是 7 晚，后者是 8 晚
- 行李和机型字段只在有可靠数据时填写，不推测
- PDF 增加总价口径、行李、中转、退改、出票方和机型对比
- 自动提示“最低价不是直飞时，哪一班直飞值得比较”
- 查询失败时自动重试一次，并可保存截图与短诊断
- CLI 与渲染 Python 自动在 `PATH`、`~/.local/bin`、`~/.flight-price-skill/.venv` 中定位

## 结构

```text
flight-price/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── schema.md
│   └── request-mapping.md
├── assets/sample-report.pdf
└── scripts/
    ├── run_flight_pdf.py     # v0.4 端到端：扫描+重试+汇总+PDF，一条命令
    ├── run_flight_query.py
    ├── flight_report.py
    └── diagnose_trip.py
examples/
├── HKG-MXP-sample.json
├── flat-scan-sample.json
└── HKG-MXP-sample.pdf
tests/
├── test_run_flight_pdf.py
└── test_report.py
```

## 安装

从本仓库的 Release 下载 ZIP，然后解压到 Codex skills 目录：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
unzip flight-price-pdf-skill.zip -d "${CODEX_HOME:-$HOME/.codex}/skills"
```

也可以克隆仓库后执行：

```bash
./install.sh
```

## 使用

### v0.4 端到端一条命令（多机场 / 日期窗口比价，推荐）

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_pdf.py" HKG,SZX,CAN,MFM HND \
  --days 7 --depart 2027-06-20 --to 2027-07-25 \
  --clamp-return 2027-07-31 --airline UO,NH,CX \
  --title "大湾区→羽田 2027 夏 往返比价" --output out.pdf
```

脚本内部完成：全窗口扫描 → `timeout` 日期对自动重试一次 → 汇总去重 → 中文 HTML → Playwright 渲染 PDF；中间 JSON 全部放临时目录并自动清理（`--keep-json` 可保留合并后的原始数据）。终端只输出 3 行以内摘要：

```text
PDF: out.pdf
HKG best ¥2135 UO UO622 06/20~06/26 直飞
queries ok=48 no_results=0 retried=3 | rows=240 | out.html
```

单程：`--trip-type oneway`；只要摘要不出 PDF：`--no-pdf`。

新开 Codex 对话，直接说：

```text
用 $flight-price 查香港到米兰，2027 年 6 月，玩 8 天，往返，生成 PDF
用 $flight-price 查深圳到东京，2027 年 4 月 3 日，单程，生成 PDF
```

也可以直接运行入口脚本：

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --trip-type roundtrip --days 8 \
  --depart 2027-06-01 --to 2027-06-30 \
  --formats pdf \
  --output "./ORIGIN-DEST-2027-06.pdf" \
  --title "机票汇总"
```

需要 Word 或 Excel 时：

```bash
--formats pdf,xlsx,docx
```

单程示例：

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" SZX NRT \
  --trip-type oneway \
  --depart 2027-04-03 --to 2027-04-03 \
  --output "./SZX-NRT-2027-04.pdf"
```

失败诊断默认写入 `./flight-diagnostics`：

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --trip-type roundtrip --stay 8 \
  --depart 2027-06-10 --to 2027-07-01 \
  --diagnostics-dir "./flight-diagnostics"
```

样例产物：

- [JSON](examples/HKG-MXP-sample.json)
- [PDF](examples/HKG-MXP-sample.pdf)

## 依赖

- `flight-price` CLI（安装后通常在 `~/.local/bin`，脚本会自动定位）
- `run_flight_pdf.py`（v0.4 端到端路径）：Python 3.9+；PDF 由 `flight-price` 自带的 Playwright 渲染，**不依赖 reportlab / python-docx / openpyxl**
- `run_flight_query.py` + `flight_report.py`（旧路径与 DOCX/XLSX）：Python 3.11+、`reportlab`、`python-docx`、`openpyxl`
- `pypdf`（仅运行完整测试时需要；缺失时相关用例自动跳过）

在 Codex 桌面版中，使用 workspace dependencies 提供的 Python 运行脚本。

## 测试

```bash
python3 -m unittest discover -s tests -v   # 全部离线测试，无需网络
```
