import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const ts = require('typescript');
const source = readFileSync(new URL('../frontend/src/offerTax.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { estimateOffer, annualTax, defaultTaxSettings, readTaxSettings, compareBonusTax, housingFund } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const salary = { monthlySalary: 10000, salaryMonths: 12, bonus: 0, signingBonus: 0, otherCompensation: 0 };
const settings = { ...defaultTaxSettings(), enabled: true, year: 2026, socialBase: 10000, socialRate: 10, fundBase: 10000, fundRate: 5 };
const result = estimateOffer(salary, settings);
assert.equal(result.tax, 1680);
assert.equal(result.net, 100320);
assert.equal(result.months[0].tax, 105);
assert.equal(result.months[11].tax, 350);
assert.equal(Math.round(result.months.reduce((s,m)=>s+m.net,0)*100), Math.round(result.net*100));
assert.equal(annualTax(36000),1080);
assert.equal(annualTax(144000),11880);
assert.equal(annualTax(300000),43080);
assert.equal(estimateOffer({...salary, monthlySalary:5000},defaultTaxSettings()).tax,0);
const bonus = estimateOffer({...salary,salaryMonths:14},{...settings,separateBonus:20000});
assert.equal(bonus.tax,2280);
assert.equal(bonus.net,119720);
assert.ok(estimateOffer(salary,{...settings,socialRate:101}).error);
assert.ok(estimateOffer(salary,{...settings,separateBonus:1}).error);
assert.ok(estimateOffer({...salary,bonus:36000},{...settings,year:2028,separateBonus:36000}).error);
assert.ok(estimateOffer({...salary,monthlySalary:NaN},settings).error);
assert.equal(readTaxSettings('invalid').enabled,false);
assert.equal(estimateOffer(salary,{...settings,deduction:10000}).tax,0);
assert.equal(estimateOffer({...salary, id: 1, companyName: '演示公司', taxSettings: JSON.stringify(settings)}, settings).net,100320);
const sh = {...settings,socialBase:15000,socialRate:10.5,fundBase:15000,fundRate:5,separateBonus:15000};
const offer = {...salary,monthlySalary:15000,salaryMonths:13};
const cmp = compareBonusTax(offer,sh);
assert.equal(cmp.combined.gross,195000);
assert.equal(cmp.combined.tax,8190);
assert.equal(cmp.combined.net,158910);
assert.equal(cmp.separate.tax,7140);
assert.equal(cmp.separate.net,159960);
assert.equal(cmp.saving,1050);
assert.equal(cmp.recommended,'separate');
const low = compareBonusTax({...salary,monthlySalary:3000,bonus:12000},{...defaultTaxSettings(),year:2026,separateBonus:12000});
assert.equal(low.combined.tax,0);
assert.equal(low.separate.tax,360);
assert.equal(low.recommended,'combined');
const neutral = compareBonusTax(salary,{...settings,separateBonus:0});
assert.equal(neutral.recommended,'equal');
// Bonus tax cliffs: selecting a rate is based on bonus/12, but tax is on the full bonus.
for(const [b,t] of [[36000,1080],[36000.01,3390],[144000,14190],[300000,58590],[420000,102340],[660000,193590],[960000,328840]]) {
 const x=estimateOffer({...salary,bonus:b},{...defaultTaxSettings(),year:2026,separateBonus:b});
 const base=estimateOffer(salary,{...defaultTaxSettings(),year:2026});
 assert.equal(Math.round((x.tax-base.tax)*100)/100,t);
}
assert.ok(compareBonusTax(offer,{...sh,year:2028}).error);
assert.ok(compareBonusTax(offer,{...sh,separateBonus:15000.01}).error);
assert.deepEqual(housingFund(15000,5,5),{personal:750,employer:750,monthly:1500,annual:18000});
assert.deepEqual(housingFund(10000,5,7),{personal:500,employer:700,monthly:1200,annual:14400});
assert.ok(housingFund(15000,5,101).error);
// Monetary identities across rates, low/high incomes and both bonus treatments.
for(const monthlySalary of [3000,5000,10000,15000,50000,100000,12345.67]) {
 for(const b of [0,10000,36000.01]) {
  for(const separateBonus of [0,b]) {
   const x=estimateOffer({...salary,monthlySalary,bonus:b},{...settings,socialBase:monthlySalary,socialRate:10.5,fundBase:monthlySalary,separateBonus});
   assert.ok(!x.error);
   assert.equal(Math.round(x.months.reduce((sum,m)=>sum+m.net,0)*100),Math.round(x.net*100));
   assert.equal(Math.round((x.gross-x.social-x.fund-x.tax)*100),Math.round(x.net*100));
   assert.ok(x.months.every(m=>m.tax>=0));
  }
 }
}
console.log('Passed tax cases: annual bands, bonus cliffs, recommendations, housing fund, invalid inputs and 42 monetary-identity scenarios.');
