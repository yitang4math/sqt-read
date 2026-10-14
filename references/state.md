# 精读与接续状态

保存`<paper>.reading.md`和`<paper>.state.json`，用户目录优先。图与报告同目录，源PDF不放技能目录，不修改原PDF。`schema_version: 1`保持兼容；来源身份与Q/C/E决定判断，展示映射不重编号固定ID。必要修订写history，不悄悄覆盖旧结论。

## 共同字段

| 字段 | 内容 |
|---|---|
| skill_version / mode / user_goal / completion | 使用版本、模式、目标及本轮完成/未决范围 |
| sources | id、kind、availability acquired/missing；本地已得文件path/sha256，PDF另有page_count/extractor/engine；准确原题、版本与标识 |
| questions | id/text/basis source或inference或unresolved/source_ids；必要时role scientific或operational、parent_id |
| claims | id/question_id/author_claim/author_locator/verdict supported或limited或counter或pending/supported_scope/reason/evidence_ids |
| evidence | id/source_id/type/locator/inspection/inspection_detail/links，links含claim_id、for/against/context及scope |
| coverage | 实读text区间、实看visual页、acquired_unread与missing；可另列current_review/inherited_unverified |
| history | id/before/after/why/evidence_ids；初次可空 |
| next | claim_id可null、location/action/decides/stop_condition；优先最多三项 |
| presentation | report_id、questions，每Q有question_id/display_label和命题claim_id/display_label映射 |

PDF locator含source_id/page，可加当前提取版本的start/end、section/table/figure。其他来源可用段落或URL。只定位的证据不能支撑已判结论；反证需同范围against证据。来源文件变动需重查，抽取版本变动需重新定位偏移。实际回显并读过才写coverage；缓存不是已读。

## 精读内容与语言

`report`含title/paper_source_id/paper_language/paper_note/scope_note/research_object/research_boundary/reading_boundary(label/text数组)。title必须与指定来源的首页完整原题一致；简称不混入。旧文字版多Q还用question_overview；图文版不要求该字段。

非中文展示Q包含`original_form`：language、kind author_quote或reader_reconstruction、derived_from: source_text、text。原句须核对并附locator；重构附source_locators数组。先据原文生成主表述，再填`translation: {language: zh, derived_from: original_form, text: 中文译文}`；兼容字段questions.text与译文一致。不能从旧中文回译后标成source_text；字段只能检查声明，不能证明生成过程。中文论文可省original_form。

Q的`report`有gap、author_answer、unanswered及非空answer_sections。每个侧面含aspect/role direct或indirect或reliability/text/claim_ids，形成综合而非拼接C摘要。可选identification_note仅解释实质识别歧义，常规重构不展示性质卡。

C的`report`有title/evidence_note及question_link：question_id指向展示科学Q、aspect、role、relevance、impact。归属不能替代如何参与回答的推理。附录判断据原C生成，不另存第二套判定。关键限制必须进入综合；次要C可只留附录。历史操作性子Q可在科学父Q下展示，不能重接到无关Q。

## 0.4图文扩展（旧状态兼容）

新精读默认`presentation.layout: graph`。每个answer_sections项新增稳定`id`，例如F1；禁止因重排改ID。显式运行`map_answer_sections(state)`，按当前展示顺序保存各Q的`answer_sections: [{section_id: F1, display_label: A1}, ...]`。图、正文标题、附录链接据此生成；A/B标签只是展示编号。

`presentation.graph`包含：

- `question_labels`：展示Q的固定ID到经过核对的短标签。
- `relations`：数组，可空。每项有稳定id、from/to展示Q ID、text连线含义、basis判断依据、claim_ids依据命题（可空，但basis不可空）。不能连接不存在的Q、自连或借无关命题支撑；概念关系可依据两Q的已核问题背景说明，不伪造C。
- `review_basis`：显式语义复核后的依据指纹，由绑定函数生成。

侧面数量与命名自由。一个C可以被多个正文侧面引用，附录只详述一次；仅附录的C无需图节点。没有依赖的多个Q可只展示各自侧面，不能自动用相邻编号连线。

## 复核与生成入口

先核正文与C/E、图关系与问题背景的意义一致，再显式运行：

```python
# report.py在当前技能scripts目录；此处的state内容须已实际复核。
report.map_answer_sections(state)
report.seal_answers(state)
```

保存新状态后执行`python scripts/report.py state.json --out reading.md`。模块函数`write_report(state, target, ...)`提供同一入口；同时生成本地PNG/SVG与报告，返回耗时、后端、警告及图路径。依赖缺失退化Mermaid并明确说明，不调用绘图模型。

0.3的claim_basis继续绑定Q、作者命题、判定、核查、C/Q关系、实际E与来源身份。0.4侧面另有review_basis绑定id/aspect/role/text/claim_ids及claim_basis；图指纹绑定问题简称、连线及依据、两端问题/综合/C/E。修改综合文字、连线含义、问题或证据后生成器拒绝旧复核，须实际复核再绑定；渲染不自动重绑。纯字体、位置、图片格式或展示重排不进入科学复核指纹。

旧0.3状态仍能生成原文字版；不能把设置skill_version改成0.4当作已完成迁移。转图版应另存、补稳定ID与关系、压缩已核综合并实际复核。原题、双语问题、旧C/E与判断保留，变化的呈现字段记history。图文本含义校验仍靠阅读者，指纹不是正确性证明。

来源可访问且本轮需要续读时先用`paper.py verify-state`检查；纯呈现改写不为校验格式重新读取PDF，注明沿用可靠记录与本轮边界。恢复材料可得时继续必要核查，不把历史未读当永久缺失。

## 成本记录

cost可分别记录本地生成秒数、实际工具往返、图像检查次数，以及可获得的模型请求/用量/费用；未知填null。原文回显字符、文档长度不代表真实计费，不能用字符除以4估算。图中文字与正文文字分开统计，开发模板成本与每篇运行成本分开；只复核改变的面板，不因配图重复全文阅读。


## 0.5关键关系图扩展

schema_version保持1，0.5系列默认presentation.layout仍为graph。不通过单改版本号迁移科学内容。沿用已核Q/C/E并建立新展示状态，节点ID与展示编号分开。0.5.1只修复连线呈现：0.5.0的可靠状态可直接重绘，原语义复核绑定保持有效，无需重新读论文或seal。

Q.report.answer_sections仍保存稳定id、aspect、role、text、claim_ids及复核依据。正文侧面不必全部入图；可引用另一Q的命题以说明实际交互，但至少有一个本Q且同role的依据命题，不借跨Q引用改写其原归属。map_answer_sections按Q顺序映射A1、B1等。

可选report.notes数组用于跨Q或旁支边界：每项id/aspect/text/claim_ids。id不与Q、侧面重复；map_answer_sections保存presentation.notes的N1/N2映射。seal_answers同时绑定旁注文字和其C/E依据。旁注不在总图重复画一组节点。

presentation.graph采用：

```json
{
  "format": "compact",
  "question_labels": {"Q1": "经过核对的问题简称"},
  "nodes": [
    {"section_id": "F_SP", "kind": "construction", "summary": "已核内容的简短表述"},
    {"section_id": "F_TEST", "kind": "support", "summary": "限定条件下的检验"}
  ],
  "relations": [
    {"id": "R1", "from": "F_TEST", "to": "F_SP", "kind": "support",
     "text": "受限支持", "basis": "原记录支持到什么程度及其限定", "claim_ids": ["C1"]}
  ],
  "layout": "auto",
  "review_basis": "由显式复核绑定生成"
}
```

nodes只选择存在的正文侧面，kind为construction/support/limit/indirect；节点的题目、展示编号、命题引用从侧面生成，summary不另设判定。relations起终点允许展示Q ID或已选section_id，kind为construction/support/limit/indirect/dependency。每条有稳定id、text、basis及claim_ids（概念依赖可空，但须有已核依据）。自连、未知节点、无关Q命题及重复ID拒绝；这不证明依据本身正确。节点与关系数量依据论文，允许空数组，绝不自动补箭头。

graph.layout仅控制auto/grouped/indexed排版，不写坐标。auto/grouped优先总图；indexed或自动拆图均保留每条关系的两个端点与实际箭头，不再只输出关系表。问题类型不构成绘图门槛。layout.json记录每条edge_routes的原关系ID、from/to、类型、文字与路径；分图的重复端点记node_instances，便于检查全部关系恰好呈现一次。图指纹新增绑定节点选择、类型和摘要、连线类型及旁注；纯layout改变可以重绘，无需再seal。渲染不会自动seal。

先实际核对语义，再map_answer_sections与seal_answers；一次运行report.py即可生成图/正文/附录。复杂关系自动拆为带端点及箭头的局部图，保留选择的节点/关系及所有问题；依赖缺失按原因退化Mermaid。cost区分生成入口、看图、修图、开发时间、单篇时间，不能把工具调用次数当模型API次数。
