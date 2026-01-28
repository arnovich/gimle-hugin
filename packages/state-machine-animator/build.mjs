/**
 * Build script for state-machine-animator
 * Uses esbuild for fast, simple bundling with no config files
 */

import * as esbuild from 'esbuild';
import { execSync } from 'child_process';
import { existsSync, mkdirSync } from 'fs';

const isWatch = process.argv.includes('--watch');

// Ensure dist directory exists
if (!existsSync('./dist')) {
  mkdirSync('./dist');
}

// Common build options
const commonOptions = {
  entryPoints: ['./src/index.ts'],
  bundle: true,
  sourcemap: true,
  target: ['es2020'],
  minify: false,
};

// ESM build
const esmBuild = {
  ...commonOptions,
  format: 'esm',
  outfile: './dist/state-machine-animator.js',
};

// CJS build
const cjsBuild = {
  ...commonOptions,
  format: 'cjs',
  outfile: './dist/state-machine-animator.cjs',
};

// Minified UMD-style IIFE build for browser script tag usage
const browserBuild = {
  ...commonOptions,
  format: 'iife',
  globalName: 'StateMachineAnimator',
  outfile: './dist/state-machine-animator.min.js',
  minify: true,
};

async function build() {
  try {
    if (isWatch) {
      // Watch mode - rebuild on changes
      const contexts = await Promise.all([
        esbuild.context(esmBuild),
        esbuild.context(cjsBuild),
        esbuild.context(browserBuild),
      ]);

      await Promise.all(contexts.map(ctx => ctx.watch()));
      console.log('Watching for changes...');
    } else {
      // One-time build
      await Promise.all([
        esbuild.build(esmBuild),
        esbuild.build(cjsBuild),
        esbuild.build(browserBuild),
      ]);

      // Generate type declarations
      console.log('Generating type declarations...');
      execSync('npx tsc --declaration --emitDeclarationOnly --outDir dist', {
        stdio: 'inherit',
      });

      console.log('Build complete!');
    }
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build();
