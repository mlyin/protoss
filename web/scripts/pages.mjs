import { copyFile, mkdir, writeFile, readdir, readFile } from 'node:fs/promises'
await mkdir('pages-dist/app', { recursive: true })
await copyFile('pages-dist/index.html', 'pages-dist/app/index.html')
await copyFile('pages-dist/index.html', 'pages-dist/404.html')
await writeFile('pages-dist/.nojekyll', '')
await writeFile('pages-dist/CNAME', 'protoss.trade\n')
async function inspect(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`
    if (entry.isSymbolicLink()) throw new Error(`Symlink in artifact: ${path}`)
    if (entry.isDirectory()) { await inspect(path); continue }
    if (/^(\.env|.*\.(db|pem|key|map))$/.test(entry.name)) throw new Error(`Forbidden file: ${path}`)
    const text = await readFile(path, 'utf8')
    if (/(?:ar_(?:owner|live|org)_[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|HL_MASTER_PRIVATE_KEY\s*=\s*0x)/.test(text)) throw new Error(`Secret pattern in ${path}`)
  }
}
await inspect('pages-dist')
console.log('Pages artifact checked: frontend files only; root and /app/ share one bundle.')
