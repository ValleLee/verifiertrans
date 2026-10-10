# qutebrowser conversion trial: public-surface limitation

## 现象

在新的逐条 F2P accounting 和 symbol provenance gate 下，qutebrowser 的 rev_001、rev_002、rev_003 都完整保留了 11 条 F2P（包括两条 `__str__` 和 Hypothesis 中的 `str()` 行为），但 semantic gate 拒绝了最终 verifier。

## 关键 evidence

- Base Repo 只有 `configutils.parse_font_families`，没有 `configutils.FontFamilies` 或 `FontFamilies.from_str`。
- Gold patch 新增 `FontFamilies` 和 `from_str`。
- Problem Statement 只描述一致的字体解析行为和标题中的 `FontFamilies` 类，没有声明 `from_str` 方法名或模块路径。
- Base 的旧解析器已经产生与历史 F2P 相同的解析结果；通过已有 QtFont/configuration 行为验证时，Base 可能与 Gold 都满足这些行为，因此不能同时保持纯功能验证和 Base 必须 FAIL 的挑战性门槛。
- 新 provenance gate 准确报告：`configutils.FontFamilies.from_str` 是 Base 不存在且 P 未声明的隐藏方法。

## failure classification

- 类型：verifier semantic / public-surface availability
- scope：instance/data-specific，不应给共享框架加入 qutebrowser 特判

## 结论

这条任务在“最终只把 Problem Statement 给 solver、verifier 只使用 P/Base 已有公开或可观察契约、同时 Base + Functional 必须 FAIL”的三项约束下没有足够的公共验证面。强行保留 `FontFamilies.from_str` 会重新引入 hidden interface binding；改用 Base 旧 parser 或 QtFont 行为又无法证明该任务的新增变化。

因此 attempt_002 应保持 `manual_review_required`，不生成 final 包。历史 F2P 的语义没有被静默 drop；它们全部被记录为 rewrite，但当前可观察边界不足以形成合格的最终 verifier。

## 验证结果

- artifact contract：PASS（11/11 F2P 有行为意图、验证面、证据和 emitted tests）
- semantic/provenance gate：FAIL（`configutils.FontFamilies.from_str` hidden contract）
- hard replay / stability / QA / package：按 gate 顺序未执行

## 对框架的影响

共享框架现在能够区分：

1. F2P 意图被错误 drop；
2. verifier 依赖 solver 看不到的接口；
3. 当前数据确实缺少可移植的 public/observable surface。

后续同类任务应在 semantic gate 阶段进入 `manual_review_required`，而不是无限 repair 或通过隐藏接口打包。

## Revision 004 follow-up (2026-09-29)

A repair removed the direct `FontFamilies.from_str` call and used `QtFont.to_py`
plus the Problem Statement-named class. The static provenance gate then passed,
and Docker replay was Base `FAIL` (46/57 required, all 11 F2P missing) and Gold
`PASS` (57/57 required). The semantic Judge still found under-conversion: an
inert `FontFamilies` class could pass because Base already exposes equivalent
parsing through the old helper and QtFont path. This confirms that the
remaining limitation is data/specification-specific, not a missing converter
loop. The run remains `manual_review_required`; no final package is produced.
