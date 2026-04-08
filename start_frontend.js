// Vite dev server launcher (from project root)
const { execSync } = require('child_process');
const path = require('path');

process.chdir(path.join(__dirname, 'frontend'));
execSync('npx vite --host', { stdio: 'inherit' });
