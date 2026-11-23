import { defineConfig } from 'vite'

// The build goes into the Python package, so the box in the car serves the app itself
// and its updater carries it. File names are fixed so that a rebuild shows up as a plain diff.
export default defineConfig({
  base: './',
  build: {
    outDir: '../src/cardiag/web/glasses',
    emptyOutDir: true,
    target: 'es2020',
    rollupOptions: {
      output: { entryFileNames: 'assets/app.js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
  // `npm run dev` beside `cardiag serve --sim focus_dct`: the page asks its own origin for values.
  server: { host: true, proxy: { '/api': process.env.CARDIAG ?? 'http://127.0.0.1:8000' } },
})
