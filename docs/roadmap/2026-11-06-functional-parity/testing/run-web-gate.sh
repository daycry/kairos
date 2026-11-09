set -eu
mkdir -p /tmp/current-web
cp -R /candidate/src /candidate/tests /candidate/public /tmp/current-web/
cp /candidate/package.json /candidate/package-lock.json /candidate/tsconfig.json /candidate/vite.config.ts /candidate/index.html /candidate/portal.html /candidate/docs.html /tmp/current-web/
ln -s /app/node_modules /tmp/current-web/node_modules
cd /tmp/current-web
mkdir -p /evidence
npm test > /tmp/web-tests.log 2>&1 || { cat /tmp/web-tests.log; exit 1; }
tail -n 9 /tmp/web-tests.log
npm run build
cp -R dist/. /evidence/
node /evidence-root/write-web-receipt.mjs
