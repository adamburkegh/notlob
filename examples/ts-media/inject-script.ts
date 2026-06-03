/**
 * notlob ~on-build hook for ts-media.
 *
 * Receives a JSON manifest (path passed as argv[2]) describing the
 * built TypeScript artifacts and external files declared in binding.lob.
 *
 * Steps:
 *  1. Bundle the built .ts artifact to inline JavaScript using esbuild's
 *     Node API (avoids shell path issues on Windows).
 *  2. Read the HTML template (index.html declared as ~external).
 *  3. Replace the <!-- notlob:bundle -->...<!-- /notlob:bundle --> region
 *     with a <script> tag containing the bundled JavaScript.
 *  4. Write the result to dist/index.html.
 *
 * Running: tsx inject-script.ts <manifest.json>
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join }                                    from 'path';
import * as esbuild                                from 'esbuild';

// ── Read manifest ─────────────────────────────────────────────

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('Usage: inject-script.ts <manifest.json>');
  process.exit(1);
}

const manifest: {
  artifacts:    string[];
  entry_points: string[];
  externals:    string[];
  language:     string;
  project_root: string;
  output_dir:   string;
} = JSON.parse(readFileSync(manifestPath, 'utf-8'));

// ── Locate inputs ─────────────────────────────────────────────

// Prefer entry-point artifacts (modules with ~run claims) over
// all artifacts — this selects the DOM entry point rather than
// a pure library module when both are in the project.
const candidates = manifest.entry_points?.length > 0
  ? manifest.entry_points
  : manifest.artifacts;
const tsArtifact   = candidates.find(p => p.endsWith('.ts'));
const htmlTemplate = manifest.externals.find(p => p.endsWith('.html'));

if (!tsArtifact) {
  console.error('inject-script: no .ts artifact in manifest');
  process.exit(1);
}
if (!htmlTemplate) {
  console.error('inject-script: no .html external in manifest');
  process.exit(1);
}

// ── Bundle TypeScript → inline JavaScript (esbuild Node API) ──

let bundledJs: string;
try {
  const result = esbuild.buildSync({
    entryPoints: [tsArtifact],
    bundle:      true,
    format:      'iife',
    write:       false,
    logLevel:    'warning',
  });
  bundledJs = result.outputFiles[0].text;
} catch (err) {
  console.error('inject-script: esbuild failed:', err);
  process.exit(1);
}

// ── Inject into HTML template ─────────────────────────────────

const html     = readFileSync(htmlTemplate, 'utf-8');
const startTag = '<!-- notlob:bundle -->';
const endTag   = '<!-- /notlob:bundle -->';

const startIdx = html.indexOf(startTag);
const endIdx   = html.indexOf(endTag);

if (startIdx === -1 || endIdx === -1) {
  console.error('inject-script: <!-- notlob:bundle --> markers not found in template');
  process.exit(1);
}

const before   = html.slice(0, startIdx);
const after    = html.slice(endIdx + endTag.length);
const injected = `${startTag}\n<script>\n${bundledJs}</script>\n${endTag}`;
const outputHtml = before + injected + after;

// ── Write output ──────────────────────────────────────────────

const outputPath = join(manifest.output_dir, 'index.html');
mkdirSync(manifest.output_dir, { recursive: true });
writeFileSync(outputPath, outputHtml, 'utf-8');

console.log(`INJECT ${outputPath}`);
