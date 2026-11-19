version 18.0
clear all
set more off
args projectroot
if `"`projectroot'"' != "" cd `"`projectroot'"'
capture mkdir results
capture log close _all
log using "results/stata_cohorts.log", text replace

* Deterministic cohort estimates: placebo distributions remain in the Python
* supplementary scripts. They are diagnostics under nonrandom policy selection.
mata:
real matrix yrmatrix(string scalar stub, real scalar start, real scalar finish)
{
    string rowvector vars
    real scalar y
    vars=J(1,finish-start+1,"")
    for(y=start;y<=finish;y++) vars[y-start+1]=stub+strofreal(y)
    return(st_data(.,vars))
}
void report(real matrix Y, string colvector names, real scalar first,
            string colvector treated, real colvector announced,
            real scalar begin, real scalar adjust, real scalar common,
            real scalar span, real scalar omit, string scalar spec,
            string scalar outcome, real scalar fh)
{
    real colvector ci,ti,allti,gs,center,eff,weight,sel
    real rowvector pre,post
    real matrix yp
    real scalar j,g,k
    allti=J(rows(treated),1,.)
    for(j=1;j<=rows(treated);j++) allti[j]=selectindex(names:==treated[j])[1]
    ci=1::rows(Y)
    for(j=1;j<=rows(allti);j++) ci=select(ci,ci:!=allti[j])
    gs=uniqrows(sort(announced,1)); eff=J(rows(gs),1,.);weight=J(rows(gs),1,0)
    for(j=1;j<=rows(gs);j++) {
        g=gs[j]
        if(g==omit) continue
        sel=selectindex(announced:==g); ti=allti[sel]
        pre=(begin..g-1):-first:+1
        post=common ? ((g+1..g+span):-first:+1) : ((g+1-first+1)..cols(Y))
        yp=Y[,pre]
        center=(pre:-mean(pre'))'
        // Each column of delta is a city-specific change for this cohort's window.
        eff[j]=mean(rowsum(Y[ti,post])/cols(post)-rowsum(yp[ti,])/cols(pre))-mean(rowsum(Y[ci,post])/cols(post)-rowsum(yp[ci,])/cols(pre))
        if(adjust) eff[j]=eff[j]-(mean(yp[ti,]*center)-mean(yp[ci,]*center))/sum(center:^2)*(mean(post')-mean(pre'))
        weight[j]=rows(ti)
        fput(fh,spec+","+outcome+","+strofreal(g)+","+strofreal(eff[j],"%21.15g")+","+strofreal(rows(ti))+","+strofreal(rows(ci)))
    }
    k=sum(weight)
    eff=editmissing(eff,0)
    fput(fh,spec+","+outcome+",pooled,"+strofreal(sum(eff:*weight)/k,"%21.15g")+","+strofreal(k)+","+strofreal(rows(ci)))
}
end

* Applicant DDD is a DID of ln(enterprise applications / university+institute
* applications). The third difference is across these two applicant categories.
local appfile "stata/public_applicants.dta"
capture confirm file "`appfile'"
if _rc local appfile "public_applicants.dta"
use "`appfile'", clear
rename v1 city
rename v2 year
gen double gap=ln(v6/v9)
gen double share=100*v6/(v6+v9)
egen cid=group(city)
keep cid city year gap share
reshape wide gap share, i(cid city) j(year)
mata:
names=st_sdata(.,"city")
treated=("济南"\"上海"\"南京"\"杭州"\"北京")
announced=(2021\2022\2022\2022\2023)
fh=fopen("results/applicant_cohorts_stata.csv","w")
fput(fh,"specification,outcome,cohort,estimate,treated_cities,comparison_cities")
gap=yrmatrix("gap",2017,2025); share=yrmatrix("share",2017,2025)
report(gap,names,2017,treated,announced,2017,0,1,2,.,"flat_comparison","log_gap",fh)
report(gap,names,2017,treated,announced,2017,1,1,2,.,"trend_adjusted_main","log_gap",fh)
report(gap,names,2017,treated,announced,2020,0,1,2,2021,"strict_2020_flat_same_cohorts","log_gap",fh)
report(gap,names,2017,treated,announced,2020,1,1,2,2021,"strict_2020_trend_same_cohorts","log_gap",fh)
report(gap,names,2017,treated,announced,2017,1,1,2,2021,"long_window_trend_same_cohorts","log_gap",fh)
report(gap,names,2017,treated,announced,2017,1,1,2,2023,"exclude_beijing_trend","log_gap",fh)
report(share,names,2017,treated,announced,2017,0,1,2,.,"enterprise_share_flat","enterprise_share_pp",fh)
report(share,names,2017,treated,announced,2017,1,1,2,.,"enterprise_share_trend","enterprise_share_pp",fh)
fclose(fh)
end

* Aggregate financing: complete common panel for loan/GDP and log loans.
local epsfile "stata/eps_city_panel.dta"
capture confirm file "`epsfile'"
if _rc local epsfile "eps_city_panel.dta"
use "`epsfile'", clear
keep if inrange(year,2018,2024)
replace city=ustrregexra(city,"市$","")
gen double ratio=loans/gdp
gen double logloan=ln(loans/10000) if loans>0
gen byte ok=!missing(ratio,logloan)
bys cid: egen nvalid=total(ok)
keep if nvalid==7
keep cid city year ratio logloan
reshape wide ratio logloan, i(cid city) j(year)
mata:
names=st_sdata(.,"city")
treated=("济南"\"上海"\"南京"\"杭州"\"合肥"\"嘉兴"\"北京")
announced=(2021\2022\2022\2022\2022\2022\2023)
fh=fopen("results/finance_cohorts_stata.csv","w")
fput(fh,"specification,outcome,cohort,estimate,treated_cities,comparison_cities")
for(i=0;i<=1;i++) for(j=0;j<=1;j++) {
    spec="trend"+strofreal(i)+"_common"+strofreal(j)
    report(yrmatrix("ratio",2018,2024),names,2018,treated,announced,2018,i,j,1,.,spec,"loan_gdp",fh)
    report(yrmatrix("logloan",2018,2024),names,2018,treated,announced,2018,i,j,1,.,spec,"log_loan",fh)
}
fclose(fh)
end
log close
