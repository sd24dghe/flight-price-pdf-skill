# flight-price-pdf-skill

本地 Codex skill，用于查询 Trip.com 实时机票并自动生成 PDF。原始 JSON 只落盘，不打印到终端或对话。

## 功能

- `flight-price` CLI 驱动 Playwright 无头 Chromium
- 默认生成 PDF
- 可选生成 XLSX 或 DOCX
- 终端只输出文件路径、行数和最便宜方案
- 支持多日期、往返、指定日期对、航司和转机筛选
- 行李和机型字段只在有可靠数据时填写，不推测
- PDF 增加总价口径、行李、中转、退改、出票方和机型对比
- 自动提示“最低价不是直飞时，哪一班直飞值得比较”
- 查询失败时自动重试一次，并可保存截图与短诊断

## 结构

```text
flight-price/
├── SKILL.md
├── agents/openai.yaml
├── references/schema.md
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
用 $flight-price 查 HKG 到 MXP，2027 年 6 月，往返 8 晚，生成 PDF
```

也可以直接运行入口脚本：

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --rt --stay 8 \
  --from 2027-06-10 --to 2027-07-01 \
  --formats pdf \
  --output "./HKG-MXP-2027-06.pdf" \
  --title "HKG-MXP 机票汇总"
```

需要 Word 或 Excel 时：

```bash
--formats pdf,xlsx,docx
```

失败诊断默认写入 `./flight-diagnostics`：

```bash
python3 "$HOME/.codex/skills/flight-price/scripts/run_flight_query.py" HKG MXP \
  --rt --stay 8 --from 2027-06-10 --to 2027-07-01 \
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
