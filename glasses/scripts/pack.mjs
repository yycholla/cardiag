// Packs the built app for the Even Hub portal, for one cardiag address.
//
//   npm run pack -- https://carbox.your-tailnet.ts.net
//
// A packaged app may only reach addresses its manifest lists, and the list cannot hold a
// wildcard, so the address goes in here: into the manifest, and into a config.json beside
// the page so the app asks that address without anything being typed on the phone.
import { execFileSync } from 'node:child_process'
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = join(dirname(fileURLToPath(import.meta.url)), '..')
const [address, packageId] = process.argv.slice(2)
let origin
try {
  origin = new URL(address).origin
} catch {
  console.error('usage: npm run pack -- <address of cardiag, such as https://carbox.your-tailnet.ts.net> [package id]')
  process.exit(2)
}
if (!origin.startsWith('http')) {
  console.error(`${address} is not an http or https address`)
  process.exit(2)
}

const built = join(here, '..', 'src', 'cardiag', 'web', 'glasses')
const work = join(here, '.pack')
rmSync(work, { recursive: true, force: true })
mkdirSync(work)
cpSync(built, join(work, 'dist'), { recursive: true })
writeFileSync(join(work, 'dist', 'config.json'), JSON.stringify({ server: origin }) + '\n')

const manifest = JSON.parse(readFileSync(join(here, 'app.json'), 'utf8'))
manifest.permissions.find((permission) => permission.name === 'network').whitelist = [origin]
if (packageId) manifest.package_id = packageId
writeFileSync(join(work, 'app.json'), JSON.stringify(manifest, null, 2) + '\n')

const sdk = JSON.parse(readFileSync(join(here, 'package.json'), 'utf8')).dependencies['@evenrealities/even_hub_sdk']
const out = join(here, 'cardiag.ehpk')
execFileSync(join(here, 'node_modules', '.bin', 'evenhub'), ['pack', join(work, 'app.json'), join(work, 'dist'), '-o', out, '--sdk-ver', sdk], { stdio: 'inherit' })
if (origin.startsWith('http://')) console.warn('Packed for a plain http address. An installed app may refuse it; see glasses/README.md.')
console.log(`${out} reaches only ${origin}`)
