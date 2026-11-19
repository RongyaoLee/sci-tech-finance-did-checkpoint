version 18.0
clear all
set more off
set type double
args projectroot
if `"`projectroot'"' != "" cd `"`projectroot'"'
capture mkdir results
capture log close _all
log using "results/stata_replication.log", text replace

* Run from the extracted source_bundle root, for example
* do stata/main.do "C:/research/source_bundle"
local epsfile "stata/eps_city_panel.dta"
capture confirm file "`epsfile'"
if _rc local epsfile "eps_city_panel.dta"
use "`epsfile'", clear
keep if inrange(year,2018,2024)
isid cid year
keep cid city year patent_grants invention_grants loans gdp science
reshape wide patent_grants invention_grants loans gdp science, i(cid city) j(year)

mata:
// Rectangular Hungarian assignment. Each treated row receives a different donor.
real colvector assignment(real matrix cost)
{
    real scalar n,m,i,j,j0,j1,i0,d,cur
    real colvector u,v,p,way,minv,used,ans
    n=rows(cost); m=cols(cost)
    u=J(n+1,1,0); v=J(m+1,1,0); p=J(m+1,1,0)
    way=J(m+1,1,0)
    for(i=1;i<=n;i++) {
        p[1]=i; j0=1; minv=J(m+1,1,.); used=J(m+1,1,0)
        do {
            used[j0]=1; i0=p[j0]; d=.; j1=.
            for(j=2;j<=m+1;j++) if(!used[j]) {
                cur=cost[i0,j-1]-u[i0+1]-v[j]
                if(cur<minv[j]) {minv[j]=cur; way[j]=j0;}
                if(minv[j]<d) {d=minv[j]; j1=j;}
            }
            for(j=1;j<=m+1;j++) {
                if(used[j]) {u[p[j]+1]=u[p[j]+1]+d; v[j]=v[j]-d;}
                else minv[j]=minv[j]-d
            }
            j0=j1
        } while(p[j0]!=0)
        do {j1=way[j0]; p[j0]=p[j1]; j0=j1;} while(j0!=1)
    }
    ans=J(n,1,.)
    for(j=2;j<=m+1;j++) if(p[j]>0) ans[p[j]]=j-1
    return(ans)
}

real matrix readyears(string scalar stub)
{
    string rowvector vars
    real scalar y
    vars=J(1,7,"")
    for(y=2018;y<=2024;y++) vars[y-2017]=stub+strofreal(y)
    return(st_data(.,vars))
}

void seven_city()
{
    string colvector names,treated,labels
    real matrix rawtotal,rawinv,rawloan,rawgdp,rawscience,total,inv,loan,gdp,science
    real matrix lt,li,lg,ll,ls,F,C,D,delta,contrast,five,signs,means
    real colvector ti,ci,ok,idx,match,ord,center,scaled
    real scalar boundary,design,j,g,last,target,k,nc,r,b,fh,ph,nout
    real rowvector years,pre,slope,estimate,pval
    names=st_sdata(.,"city")
    treated=("济南市"\"上海"\"南京市"\"杭州市"\"合肥市"\"嘉兴市"\"北京")
    rawtotal=readyears("patent_grants"); rawinv=readyears("invention_grants")
    rawloan=readyears("loans"); rawgdp=readyears("gdp"); rawscience=readyears("science")
    ti=J(7,1,.)
    for(j=1;j<=7;j++) ti[j]=selectindex(names:==treated[j])[1]
    years=(2021,2022,2022,2022,2022,2022,2023)
    fh=fopen("results/seven_city_stata.csv","w")
    ph=fopen("results/pairs_stata.csv","w")
    fput(fh,"boundary,outcome,matched,paired_estimate,paired_conditional_p,eligible_donors")
    fput(ph,"boundary,outcome,city,control,contrast")
    signs=J(128,7,1)
    for(b=0;b<128;b++) for(j=1;j<=7;j++) signs[b+1,j]=2*mod(floor(b/2^(j-1)),2)-1
    for(boundary=1;boundary<=2;boundary++) {
        total=rawtotal; inv=rawinv; loan=rawloan; gdp=rawgdp; science=rawscience
        if(boundary==1) {
            r=selectindex(names:=="莱芜市")[1]
            total[ti[1],1]=total[ti[1],1]+total[r,1]
            inv[ti[1],1]=inv[ti[1],1]+inv[r,1]
            loan[ti[1],1]=loan[ti[1],1]+loan[r,1]
            gdp[ti[1],1]=gdp[ti[1],1]+gdp[r,1]
            science[ti[1],1]=science[ti[1],1]+science[r,1]
        }
        ok=(rowsum(total:>=.):==0):&(rowsum(inv:>=.):==0):&(rowsum(inv:<0):==0):&(rowsum(total:<inv):==0)
        ok=ok :& (rowsum(gdp[,1..5]:<=0):==0):&(rowsum(loan[,1..5]:<=0):==0):&(rowsum(science[,1..5]:<=0):==0)
        ok=ok :& (rowsum(gdp[,1..5]:>=.):==0):&(rowsum(loan[,1..5]:>=.):==0):&(rowsum(science[,1..5]:>=.):==0)
        assert(all(ok[ti])); ci=selectindex(ok)
        for(j=1;j<=7;j++) ci=select(ci,ci:!=ti[j])
        nc=rows(ci); assert(nc==256)
        lt=ln(1:+total); li=ln(1:+inv); lg=ln(gdp); ll=ln(loan); ls=ln(science)
        for(design=1;design<=2;design++) {
            nout=design==1 ? 4 : 2
            D=J(7,nc,.); delta=J(rows(total),7*nout,.)
            for(j=1;j<=7;j++) {
                g=years[j]; last=g-2018-(design==2); pre=1..last
                target=design==1 ? g+1-2017 : g-1-2017
                F=(rowsum(lt[,pre])/last, lt[,last]-lt[,1], rowsum(lg[,pre])/last, rowsum(ls[,pre])/last, rowsum(ll[,pre])/last)
                slope=sqrt(diagonal(variance(F[ci,])))'
                C=(F[ci,]-J(nc,1,1)*F[ti[j],]):/(J(nc,1,1)*slope)
                D[j,]=sqrt(rowsum(C:^2))'
                k=(j-1)*nout
                delta[,k+1]=lt[,target]-rowsum(lt[,pre])/last
                delta[,k+2]=li[,target]-rowsum(li[,pre])/last
                if(design==1) {
                    center=(pre:-mean(pre'))'
                    delta[,k+3]=delta[,k+1]-(lt[,pre]*center/sum(center:^2))*(target-mean(pre'))
                    delta[,k+4]=delta[,k+2]-(li[,pre]*center/sum(center:^2))*(target-mean(pre'))
                }
            }
            match=assignment(D); contrast=J(7,nout,.); five=J(7,nout,.)
            for(j=1;j<=7;j++) {
                k=(j-1)*nout; idx=(k+1..k+nout)'
                contrast[j,]=delta[ti[j],idx']-delta[ci[match[j]],idx']
                ord=order((D[j,]',ci),(1,2))
                five[j,]=delta[ti[j],idx']-mean(delta[ci[ord[1..5]],idx'])
            }
            estimate=mean(contrast); means=signs*contrast/7
            pval=colsum(abs(means):>=J(128,1,1)*(abs(estimate):-1e-12))/128
            labels=design==1 ? ("log_patent_grants"\"log_invention_grants"\"total_after_pretrend"\"invention_after_pretrend") : ("total_pre_holdout"\"invention_pre_holdout")
            for(k=1;k<=nout;k++) {
                fput(fh,(boundary==1 ? "same_boundary" : "as_reported")+","+labels[k]+","+invtokens(strofreal((mean(five[,k]),estimate[k],pval[k],nc),"%21.15g"),","))
                for(j=1;j<=7;j++) fput(ph,(boundary==1 ? "same_boundary" : "as_reported")+","+labels[k]+","+treated[j]+","+names[ci[match[j]]]+","+strofreal(contrast[j,k],"%21.15g"))
            }
        }
    }
    fclose(fh);fclose(ph)
}
seven_city()
end

* Re-estimate patent-type DDD from the raw EPS observations, as in v11.
use "`epsfile'", clear
keep if inrange(year,2018,2024)
gen double other=patent_grants-invention_grants
gen double patent_gap=ln(1+invention_grants)-ln(1+other) if other>=0 & !missing(other,invention_grants)
bysort cid: egen nvalid=count(patent_gap)
keep if nvalid==7
gen int onset=.
replace onset=2022 if city=="济南市"
replace onset=2023 if inlist(city,"上海","南京市","杭州市","合肥市","嘉兴市")
replace onset=2024 if city=="北京"
gen byte D=(year>=onset) & onset<.
areg patent_gap D i.year, absorb(cid) vce(cluster cid)
scalar ddd=_b[D]
scalar ddd_se=_se[D]
preserve
clear
set obs 1
gen double coefficient=scalar(ddd)
gen double cluster_se=scalar(ddd_se)
gen double cluster_p=2*ttail(e(df_r),abs(coefficient/cluster_se))
gen double normal_reference_p=2*normal(-abs(coefficient/cluster_se))
export delimited using "results/patent_type_ddd_stata.csv", replace
restore

* EPS city PPML baseline. This checks the macro panel; the original high-tech
* enterprise PPML input panel has not been recovered, so its table is not reproduced.
poisson patent_grants D i.cid i.year, vce(cluster cid) nolog
estimates save "results/eps_patent_ppml.ster", replace
log close
