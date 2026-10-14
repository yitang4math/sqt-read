# 原文定位工具

`scripts/paper.py` 需要Python 3.9+和PyMuPDF，可执行而无需加载源码；所有路径按实际环境给出。它读取PDF字节后计算SHA256，再从同一字节提取；缓存按内容、提取器及库版本隔离。每次先验证源文件存在。缓存只是性能优化，不是已读证明。

```text
python scripts/paper.py inspect paper.pdf
python scripts/paper.py read paper.pdf --pages 1-2 --limit 12000 --save packet.json
python scripts/paper.py read paper.pdf --pages 2 --offset 3500 --limit 6000
python scripts/paper.py search paper.pdf --query "we do not" --limit 10 --offset 0
python scripts/paper.py render paper.pdf --page 3 --out page-3.png
python scripts/paper.py verify-state reading.state.json
```

`--pages`支持`1,3-5`，采用PDF物理页码。read返回原文片段的页码与字符起止、完整/部分状态、剩余页及续读偏移。完整只表示选定区间完成，不表示全文或摘要完整；模型必须确认摘要/章节边界。`source_characters`只计实际片段字符，包含重复回显，不是真实token或工具包装费用。

search默认检索全部页，包括引用与附录；按原文来源判断命中用途。它归一空白、大小写及行末连字符，保留原始位置，并报告总命中、展示数、略去数、下一偏移。归一化可能改变词形，命中只用于定位，引用与判断须核原片段。允许跨页短语；文本抽取顺序或扫描页仍可能造成漏检。零命中仅表示当前文本索引未命中。没有“最强句”排序。

inspect输出每页字符数、空文本/可疑字符提示及元数据；不判断文件是不是完整学术论文，需检查首页、目录与内容。read遇空文本仍返回明确诊断；render输出页图路径，之后用图像工具实际查看，不能把已渲染写成已视觉核查。混合扫描PDF中各页状态独立处理。

源码字符偏移针对本工具当前文本提取版本，不能跨提取器沿用。`--save`保存与stdout相同的包；保存不意味着已经读过。缓存损坏会重新提取；源版本改变时既有状态检查会失败，历史记录保留而不自动升级。

verify-state检查ID引用、已核范围、来源身份及关键判定是否有相应已检查证据；不验证原句语义、反证逻辑或实验可信度。验证通过不等于论文判断正确。
