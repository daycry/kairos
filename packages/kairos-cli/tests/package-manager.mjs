import fs from 'node:fs';
import path from 'node:path';
// Avoid shell=true and .cmd interpolation on Windows, including roots with spaces.
export function packageManager(name,args) {
  if(!['npm','npx'].includes(name)) throw Error('unknown_package_manager');
  if(process.platform!=='win32') return {command:name,args};
  const candidates=[process.env.npm_execpath,path.join(path.dirname(process.execPath),'node_modules','npm','bin','npm-cli.js')].filter(Boolean);
  const npm=candidates.find(candidate=>path.basename(candidate)==='npm-cli.js'&&fs.existsSync(candidate));
  if(!npm) throw Error('npm_cli_not_found_beside_node');
  const script=path.join(path.dirname(npm),name==='npm'?'npm-cli.js':'npx-cli.js');
  if(!fs.existsSync(script)) throw Error('npm_cli_not_found_beside_node');return {command:process.execPath,args:[script,...args]};
}
