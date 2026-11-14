import { parentPort, workerData } from 'node:worker_threads';
import { analyzeInWorker } from './code-analysis.mjs';
try { parentPort.postMessage({result:await analyzeInWorker(workerData.root,workerData.name,workerData.args)}); }
catch(error) {parentPort.postMessage({error:/^[a-z0-9_]{1,80}$/.test(error.message)?error.message:'code_analysis_failed'});}
