* 科创金融试验区：同期城市面板的 Stata 原生双向固定效应复算
* 运行：先进入 Research_Package 目录，再执行 do "代码/科创金融_复算.do"
* 也可将 Research_Package 的目录作为第一个参数传入。
* 输入面板由随附 Python 脚本从月度统计、2020 年人口及政策时间表生成。
* 本脚本自动识别结果与图表下首年为 2018 的新增样本目录。

version 18.0
clear all
set more off

args package_root
if `"`package_root'"' == "" local package_root "."
quietly cd `"`package_root'"'

* 批处理启动日志含本机许可信息；交付日志由 Stata 直接写入纯文本。
capture log close _all
capture mkdir "结果与图表/Stata复算"
tempname report
file open `report' using "结果与图表/Stata复算/复算日志.txt", ///
    write text replace
file write `report' "Stata native TWFE replication" _n
file write `report' "Stata version: " (c(stata_version)) _n
file write `report' "Unit: city-year; city and year fixed effects; city-clustered standard errors" _n
file write `report' "Balanced city eligibility matches the Python --balanced option." _n

* 基准四组固定；新增 2018 组按面板实际最早年份识别，避免依赖目录命名。
local source2018 ""
local found2018 0
local subdirs : dir "结果与图表" dirs "*"
foreach subdir of local subdirs {
    capture confirm file "结果与图表/`subdir'/主口径/同期城市面板.csv"
    if !_rc {
        quietly import delimited using "结果与图表/`subdir'/主口径/同期城市面板.csv", ///
            clear varnames(1) encoding("UTF-8") asdouble
        quietly summarize year, meanonly
        if r(min) == 2018 & r(max) == 2023 {
            local source2018 "结果与图表/`subdir'"
            local found2018 = `found2018' + 1
        }
    }
}
if `found2018' > 1 {
    display as error "Found multiple 2018-2023 panel directories; retain only one."
    file close `report'
    exit 459
}

tempfile results
tempname handle
postfile `handle' str12 window str12 scope str32 outcome ///
    double estimate double cluster_se double conventional_p ///
    long observations int city_clusters treated_cities df_r ///
    using `results', replace

forvalues mode = 1/3 {
    local source ""
    if `mode' == 1 {
        local source "结果与图表"
        local window "2020-2023"
        local first_year 2020
    }
    if `mode' == 2 {
        local source "结果与图表/延长政策前样本"
        local window "2019-2023"
        local first_year 2019
    }
    if `mode' == 3 & `"`source2018'"' != "" {
        local source `"`source2018'"'
        local window "2018-2023"
        local first_year 2018
    }

    if `"`source'"' != "" {
        foreach scope in main four_digit {
            local scope_dir "主口径"
            if "`scope'" == "four_digit" local scope_dir "仅四位小类"
            local input `"`source'/`scope_dir'/同期城市面板.csv"'
            capture confirm file `"`input'"'
            if _rc {
                if `mode' < 3 {
                    display as error "Required panel missing: `input'"
                    postclose `handle'
                    file close `report'
                    exit 601
                }
                file write `report' "Optional 2018 panel pending: `scope'" _n
            }
            else {
                import delimited using `"`input'"', clear varnames(1) ///
                    encoding("UTF-8") asdouble
                isid city_code year
                assert inrange(year, `first_year', 2023)
                assert inlist(benchmark_eligible, 0, 1)
                assert inlist(treated, 0, 1)
                quietly summarize year, meanonly
                assert r(min) == `first_year' & r(max) == 2023
                * 与 Python 的 --balanced 完全相同：每市须具备除过渡年外的全部年份。
                bysort city_code: egen int eligible_count = total(benchmark_eligible == 1)
                generate byte expected_count = 2024 - `first_year' - ///
                    inrange(transition_year, `first_year', 2023)
                replace benchmark_eligible = 0 if eligible_count != expected_count
                file write `report' "Panel: `window' / `scope'" _n

                foreach outcome in hightech_per_10k hightech log_hightech ///
                    manufacturing services hightech_share all_new_per_10k {
                    quietly regress `outcome' treated i.city_code i.year ///
                        if benchmark_eligible == 1, vce(cluster city_code)
                    local b = _b[treated]
                    local se = _se[treated]
                    local n = e(N)
                    local g = e(N_clust)
                    local df = e(df_r)
                    local p = 2 * ttail(`df', abs(`b' / `se'))
                    quietly levelsof city_code if e(sample) & treated == 1, ///
                        local(treated_codes)
                    local tc : word count `treated_codes'
                    post `handle' ("`window'") ("`scope'") ("`outcome'") ///
                        (`b') (`se') (`p') (`n') (`g') (`tc') (`df')
                    file write `report' "  `outcome'" ///
                        " b=" %16.10g (`b') " se=" %16.10g (`se') ///
                        " p=" %12.6g (`p') " N=" %6.0f (`n') ///
                        " G=" %4.0f (`g') _n
                }
            }
        }
    }
}

postclose `handle'
use `results', clear
sort window scope outcome
format estimate cluster_se conventional_p %21.15g
export delimited using "结果与图表/Stata复算/Stata_TWFE_原生结果.csv", ///
    replace datafmt
file write `report' "Completed " %3.0f (_N) " Stata regressions." _n
file close `report'
