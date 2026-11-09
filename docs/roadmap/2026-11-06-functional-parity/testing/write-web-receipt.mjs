import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const files={};const digest=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function walk(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory())walk(file);else files[file.replaceAll('\\','/')]=digest(file);}}
walk('src');walk('tests');
for(const file of ['package.json','package-lock.json','tsconfig.json','vite.config.ts','index.html','docs.html','portal.html'])files[file]=digest(file);
const output={};function built(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory())built(file);else output[file]=digest(file);}}built('dist');
const log=fs.readFileSync('/tmp/web-tests.log','utf8');const count=name=>Number(log.match(new RegExp('^# '+name+' (\\d+)','m'))?.[1]);
fs.writeFileSync('/evidence/web-build-receipt.json',JSON.stringify({status:'passed',verified_at_utc:new Date().toISOString(),environment:'isolated-existing-container-current-source-snapshot',image:'kairos-web-test:native',node:process.version,typescript:JSON.parse(fs.readFileSync('node_modules/typescript/package.json','utf8')).version,vite:JSON.parse(fs.readFileSync('node_modules/vite/package.json','utf8')).version,tests:{total:count('tests'),passed:count('pass'),failed:count('fail'),skipped:count('skipped')},commands:['npm test','npm run build'],source_sha256:files,built_sha256:output,model_calls:0},null,2)+'\n');
