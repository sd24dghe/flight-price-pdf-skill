# flight-price-pdf-skill

[中文](README.md) | [English](README.en.md)

本地 Codex skill，可查询任意出发地和目的地的 Trip.com 实时机票，并自动生成 PDF。支持单程、往返、玩几天或住几晚，原始 JSON 只落盘，不打印到终端或对话。

## 功能

- `flight-price` CLI 驱动 Playwright 无头 Chromium
- 默认生成 PDF
- 可选生成 XLSX 或 DOCX
- 终端只输出文件路径、行数和最便宜方案
- 支持任意出发地/目的地、单程/往返、多日期、指定日期对、航司和转机筛选
- 理解“玩 8 天”与“住 8 晚”的区别：前者是 7 晚，后者是 8 晚
- 行李和机型字段只在有可靠数据时填写，不推测
- PDF 增加总价口径、行李、中转、退改、出票方和机型对比
- 自动提示“最低价不是直飞时，哪一班直飞值得比较”
- 查询失败时自动重试一次，并可保存截图与短诊断

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
    ├── run_flight_query.py
    ├── flight_report.py
    └── diagnose_trip.py
examples/
├── HKG-MXP-sample.json
└── HKG-MXP-sample.pdf
tests/test_report.py
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

新开一个 Codex 对话，直接说：

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

- `flight-price` CLI
- Python 3.11+
- `reportlab`
- `python-docx`
- `openpyxl`
- `pypdf`（仅运行测试时需要）

在 Codex 桌面版中，使用 workspace dependencies 提供的 Python 运行脚本。

## 测试

```bash
python3 tests/test_report.py -v
```
