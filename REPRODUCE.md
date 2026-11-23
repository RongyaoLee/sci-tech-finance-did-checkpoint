# 复现说明

## 工商登记研究

使用[研究包的复现说明](Research_Package/可复现说明.md)和[代码说明](Research_Package/代码/README.md)，从城市月度汇总与同期城市面板复算结果。

## Day 3 早期分析

在 Stata/MP 18 中将工作目录设为仓库根目录，运行以下命令。

```stata
do main.do
do cohort_models.do
```

`main.do` 使用 `eps_city_panel.dta`，复算七城专利匹配、专利类型三重差分和城市专利总授权 PPML。`cohort_models.do` 使用城市面板和 `public_applicants.dta`，复算申请人类型三重差分与分批次融资估计。申请人变量见[字段表](applicant_dictionary.csv)。

结果写入 `results/`。已有逐项对照见[跨软件核对结果](cross_language_validation.json)。
